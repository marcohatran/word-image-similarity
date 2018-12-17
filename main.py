import argparse
import os, sys
import torch
import torch.optim as optim
from torchvision import datasets
from time import time



parser = argparse.ArgumentParser(description='Word Image similarity training script')
parser.add_argument('--data', type=str, default='../pair-dataset', metavar='D',
                    help="folder where data is located.")
parser.add_argument('--batch-size', type=int, default=32, metavar='B',
                    help='input batch size for training (default: 32)')
parser.add_argument('--epochs', type=int, default=10, metavar='N',
                    help='number of epochs to train (default: 10)')
parser.add_argument('--lr', type=float, default=0.1, metavar='LR',
                    help='learning rate (default: 0.01)')
parser.add_argument('--momentum', type=float, default=0.5, metavar='M',
                    help='SGD momentum (default: 0.5)')
parser.add_argument('--seed', type=int, default=1, metavar='S',
                    help='random seed (default: 1)')
parser.add_argument('--log-interval', type=int, default=10, metavar='N',
                    help='how many batches to wait before logging training status')
parser.add_argument('--experiment', type=str, default='..results/experiment', metavar='E',
                    help='folder where experiment outputs are located.')
parser.add_argument('--nb-workers', type=int, default=1)
parser.add_argument('--gpu', type=int, default=0)

args = parser.parse_args()

use_cuda = torch.cuda.is_available()


from models import TwoChannelsClassifier

model = TwoChannelsClassifier()

from data import train_transform, validation_transform

train_loader = torch.utils.data.DataLoader(
    datasets.ImageFolder(args.data + '/train',
                         transform=train_transform()),
    batch_size=args.batch_size, shuffle=True, num_workers=args.nb_workers
)

val_loader = torch.utils.data.DataLoader(
    datasets.ImageFolder(args.data + '/eval',
                         transform=validation_transform()),
    batch_size=args.batch_size, shuffle=False, num_workers=args.nb_workers)

if use_cuda:
    print('Using GPU')
    model.cuda(args.gpu)
else:
    print('Using CPU')

optimizer = optim.SGD(model.parameters(), lr=0.01, momentum=0.9, weight_decay=0.0002)

def train(epoch):

    model.train()
    correct = 0
    for batch_idx, (data, target) in enumerate(train_loader):
        if use_cuda:
            data, target = data.cuda(args.gpu), target.cuda(args.gpu)
        optimizer.zero_grad()
        output = model(data)
        criterion = torch.nn.CrossEntropyLoss(reduction='elementwise_mean')
        loss = criterion(output, target)
        loss.backward()
        optimizer.step()
        pred = output.data.max(1, keepdim=True)[1]
        correct += pred.eq(target.data.view_as(pred)).cpu().sum()
        if batch_idx % args.log_interval == 0:
            print('Train Epoch: {} [{}/{} ({:.0f}%)]\tLoss: {:.6f}'.format(
                epoch, batch_idx * len(data), len(train_loader.dataset),
                100. * batch_idx / len(train_loader), loss.data.item()))
    
    print('\nTraining score: {}/{} ({:.0f}%)\n'.format(
        correct, len(train_loader.dataset), 100. * correct / len(train_loader.dataset)
    ))

    return 100. * correct / len(train_loader.dataset)

def validation():
    with torch.no_grad():
        model.eval()
        validation_loss = 0
        correct = 0
        for data, target in val_loader:
            if use_cuda:
                data, target = data.cuda(args.gpu), target.cuda(args.gpu)
            output = model(data)
            # sum up batch loss
            criterion = torch.nn.CrossEntropyLoss(reduction='elementwise_mean')
            validation_loss += criterion(output, target).data.item()
            # get the index of the max log-probability
            pred = output.data.max(1, keepdim=True)[1]
            correct += pred.eq(target.data.view_as(pred)).cpu().sum()

        validation_loss /= len(val_loader.dataset)
        print('\nValidation set: Average loss: {:.4f}, Accuracy: {}/{} ({:.0f}%)\n'.format(
            validation_loss, correct, len(val_loader.dataset),
            100. * correct / len(val_loader.dataset)))
    
        return 100. * correct / len(val_loader.dataset)

times = []
train_score = []
test_score = []

if not os.path.exists(args.experiment):
    os.makedirs(args.experiment)


for epoch in range(1, args.epochs + 1):
    try:
        t = time()
        train_score.append(train(epoch))
        test_score.append(validation())
        model_file = args.experiment + '/model_' + str(epoch) + '.pth'
        torch.save(model.state_dict(), model_file)
        print('\nSaved model to ' + model_file + '. You can run `python evaluate.py --model ' + model_file + '` to generate the Kaggle formatted csv file')
        times.append(time() - t)
        print("Elapsed time: ", times[-1])
    except KeyboardInterrupt:
        break