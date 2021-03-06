# callbacks.py

import albumentations as A
from albumentations.pytorch import ToTensorV2

import torch
from torch.nn import functional as F

from pytorch_lightning.callbacks import Callback

import wandb

from src.dataset import ComposeMany  #, MNISTDataModule2
from src.utils import knn_monitor



class ImagePredictionLogger(Callback):
    '''Modified from
    https://colab.research.google.com/drive/12oNQ8XGeJFMiSBGsQ8uth8TaghVBC9H3'''
    def __init__(self, dataloader, n_samples=32):
        super().__init__()
        self.n_samples = n_samples
        self.x, self.y = next(iter(dataloader))

    def get_pred_probs(self, pl_module):
        '''Get prediction probabilities for `self.samples`.'''
        x = self.x.to(device=pl_module.device)  # Tensors to CPU
        y = self.y.to(device=pl_module.device)
        logits = pl_module(x)  # Model prediction
        probs = torch.max(F.softmax(logits, dim=1), -1).values
        #probs = torch.max(probs, -1).values
        preds = torch.argmax(logits, -1)
        ## Sort the validation predictions by wrong probability.
        ## See if classes match. Wrong classes have a minus sign.
        ## Then rank by prob.
        sign_correct = 2*(preds == y) - 1  # 1 correct / -1 incorrect
        _, ix_sorted = torch.sort(probs * sign_correct)
        ix = ix_sorted[:self.n_samples]
        return (x[ix], preds[ix], probs[ix], y[ix])

    def on_validation_epoch_end(self, trainer, pl_module):
        x, preds, probs, y = self.get_pred_probs(pl_module)
        ## Log the images as wandb Image
        trainer.logger.experiment.log(
            {
                "examples":[
                    wandb.Image(img, caption=f"P({pred})={prob:.2f}, Label:{img_class}")
                    for img, pred, prob, img_class in zip(x, preds, probs, y)
                ]
            }
        )


class knnMonitorLogger(Callback):
    def __init__(self, memory_dataloader, test_dataloader, knn_k, knn_t=1):
        super().__init__()
        self.memory_dataloader = memory_dataloader
        self.test_dataloader = test_dataloader
        self.knn_k = knn_k
        self.knn_t = knn_t

    def on_validation_epoch_end(self, trainer, pl_module):
        knn_monitor(pl_module.backbone.f, self.memory_dataloader, self.test_dataloader,
                    knn_k=self.knn_k, device=pl_module.device, epoch='')