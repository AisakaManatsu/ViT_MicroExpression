import timm
import torch.nn as nn
import torch.optim as optim
import torch.utils.data
import torchvision.datasets as datasets
import torchvision.transforms as transforms

from PIL import ImageFile
from tensorboardX import SummaryWriter
from torchtoolbox.tools import mixup_data, mixup_criterion
from torchtoolbox.transform import Cutout
from tqdm import tqdm

from models import *
from utils import load_for_transfer_learning

# 设置全局参数
LR = 1e-4
BATCH_SIZE = 32
EPOCHS = 30
DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
ACC = 0
ImageFile.LOAD_TRUNCATED_IMAGES = True

if __name__ == '__main__':
    # Data pretreatment
    transform_train = transforms.Compose([
        transforms.Resize(224),
        transforms.CenterCrop(224),
        transforms.RandomHorizontalFlip(),
        # transforms.RandomVerticalFlip(),
        Cutout(),
        transforms.ToTensor(),
        transforms.Normalize([0.5322349, 0.42449042, 0.37209076], [0.24563423, 0.21720581, 0.20604016])
    ])
    transform_test = transforms.Compose([
        transforms.Resize(224),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize([0.5322349, 0.42449042, 0.37209076], [0.24563423, 0.21720581, 0.20604016])
    ])

    # Load data
    dataset_train = datasets.ImageFolder('./data_train/train', transform=transform_train)
    dataset_test = datasets.ImageFolder("./data_train/val", transform=transform_test)
    print(dataset_train.class_to_idx)
    train_loader = torch.utils.data.DataLoader(dataset_train, batch_size=BATCH_SIZE, shuffle=True)
    test_loader = torch.utils.data.DataLoader(dataset_test, batch_size=BATCH_SIZE, shuffle=False)

    # Instantiate the model and move it to the GPU
    criterion = nn.CrossEntropyLoss()

    # Load model

    # VGG
    # model = timm.models.vgg19(pretrained=True, num_classes=3)

    # ResNet
    # model = timm.models.resnet18(pretrained=True, num_classes=3)

    # ViT
    # model = timm.models.vit_base_patch16_224(pretrained=True, num_classes=3)
    # model = timm.models.vit_large_patch16_224(pretrained=True, num_classes=3)

    # Swin-Transformer
    model = timm.models.swin_base_patch4_window7_224(pretrained=True, num_classes=3)

    # T2T-Vit
    # model = t2t_vit_14()
    # load_for_transfer_learning(model, "./pretrainedModels/81.5_T2T_ViT_14.pth.tar", use_ema=True, strict=False, num_classes=3)

    # num_ftrs = model.head.in_features
    # model.head = nn.Linear(num_ftrs, 3, bias=True)
    # nn.init.xavier_uniform_(model.head.weight)

    model.to(DEVICE)

    # Adam optimizer, learning rate uses cos reduced
    adam = optim.Adam(model.parameters(), lr=LR)
    optimizer = optim.lr_scheduler.CosineAnnealingLR(optimizer=adam, T_max=20, eta_min=1e-9)

    # tensorboardX
    writer = SummaryWriter("logs")

    for epoch in range(1, EPOCHS + 1):
        # train
        model.train()
        train_sum_loss = 0
        loop = tqdm(enumerate(train_loader), total=len(train_loader))
        for batch_idx, (data, target) in loop:
            data, target = data.to(DEVICE, non_blocking=True), target.to(DEVICE, non_blocking=True)
            data, labels_a, labels_b, lam = mixup_data(data, target)
            adam.zero_grad()
            output = model(data)
            loss = mixup_criterion(criterion, output, labels_a, labels_b, lam)
            loss.backward()
            adam.step()
            lr = adam.state_dict()['param_groups'][0]['lr']
            train_sum_loss += loss.data.item()
            # 更新信息
            loop.set_description(f'Epoch [{epoch}/{EPOCHS}] Batch')
            loop.set_postfix(train_loss_batch=loss.data.item(),
                             train_loss_epoch=train_sum_loss / BATCH_SIZE,
                             lr=lr)
        optimizer.step()
        writer.add_scalar("Loss", train_sum_loss / BATCH_SIZE, epoch)

        # eval
        model.eval()
        test_loss = 0
        correct = 0
        with torch.no_grad():
            for data, target in tqdm(test_loader):
                data, target = data.to(DEVICE), target.to(DEVICE)
                output = model(data)
                loss = criterion(output, target)
                _, pred = torch.max(output.data, 1)
                correct += torch.sum(pred == target)
                print_loss = loss.data.item()
                test_loss += print_loss
            correct = correct.data.item()
            acc = correct / len(test_loader.dataset)
            avgloss = test_loss / len(test_loader)
            print('Val set: Average loss: {:.4f}, Accuracy: {}/{} ({:.1f}%)'.format(
                avgloss, correct, len(test_loader.dataset), 100 * acc))
            if acc > ACC:
                torch.save(model,
                           './savedModels/' + str(model._get_name()) + '_' + str(epoch) + '_' + str(
                               round(acc, 3)) + '.pth')
                ACC = acc
        writer.add_scalar("Accuracy", acc, epoch)

    # Close drawing after training
    writer.close()
