import torchvision.transforms as transforms
import torch.utils.data as data
import torch
from PIL import Image
import os
from tqdm import tqdm
import pickle as pk
import numpy as np

def keep2chan(x):
    return x[:2,:,:]

def train_transform():
    return transforms.Compose([
        transforms.ToTensor(),
        transforms.Pad(np.random.randint(-10,11, size=2)),
        transforms.CenterCrop(size=(100,40)),
        transforms.Lambda(keep2chan),
        transforms.Normalize(mean=[0.45, 0.45], std=[0.22, 0.22])
    ])

def validation_transform():
    return transforms.Compose([
        transforms.ToTensor(),
        transforms.Pad(np.random.randint(-10,11, size=2)),
        transforms.CenterCrop(size=(100,40)),
        transforms.Lambda(keep2chan),
        transforms.Normalize(mean=[0.45, 0.45], std=[0.22, 0.22])
    ])

train_transform_before = transforms.Resize((40, 100))
validation_transform_before = transforms.Resize((40, 100))     

train_transform_after = transforms.Normalize(mean=[0.45, 0.45], std=[0.22, 0.22])
validation_transform_after = transforms.Normalize(mean=[0.45, 0.45], std=[0.22, 0.22])



def grey_pil_loader(path):
    # open path as file to avoid ResourceWarning (https://github.com/python-pillow/Pillow/issues/835)
    with open(path, 'rb') as f:
        img = Image.open(f)
        return img.convert("L")


class ManuallyBalancedController():

    def __init__(self, root, loader=grey_pil_loader,
                true_period=3,
                split_ratio=0.7,
                transform_eval_before=None,
                transform_eval_after=None,
                transform_before=None, 
                transform_after=None,
                transform_true_before=None,
                transform_true_after=None,
                nb_words_train=None,
                nb_words_val=None,
                verbose=1):
        
        words_train = {}
        words_eval = {}
        length = 0

        with open(os.path.join(root, "words.txt"), "r") as f:
            if verbose > 0:
                print("Loading list of words", end="")
            for i, line in enumerate(f):
                w = line.strip()
                if np.random.random() < split_ratio:
                    if w not in words_train.keys():
                        words_train[w] = [i + 1]
                    else:
                        words_train[w].append(i + 1)
                else:
                    if w not in words_eval.keys():
                        words_eval[w] = [i + 1]
                    else:
                        words_eval[w].append(i + 1)
                length = i
            if verbose > 0:
                print("OK")
        
        if verbose > 0:
            print("Sorting words by number of occurences", end="")
        sortedWords_train = sorted(list(words_train.keys()), key=lambda x: words_train[x], reverse=True)
        sortedWords_eval = sorted(list(words_eval.keys()), key=lambda x: words_eval[x], reverse=True)
        if verbose > 0:
            print("OK")

        self.training_set = ManuallyBalancedDataSet(
            root, words_train, sortedWords_train, loader=loader,
            true_period = true_period,
            transform_before = transform_before,
            transform_after = transform_after,
            transform_true_before = transform_true_before,
            transform_true_after = transform_true_after,
            nb_words=nb_words_train
        )

        self.evaluation_set = ManuallyBalancedDataSet(
            root, words_eval, sortedWords_eval, loader=loader,
            true_period = true_period,
            transform_before = transform_eval_before,
            transform_after = transform_eval_after,
            transform_true_before = None,
            transform_true_after = None,
            nb_words=nb_words_val
        )
        

class ManuallyBalancedDataSet(data.Dataset):

    def __init__(self, root, indices, sortedWords, 
                loader=grey_pil_loader,
                true_period=3,
                transform_before=None, 
                transform_after=None,
                transform_true_before=None,
                transform_true_after=None,
                nb_words=None):
        if nb_words == None:
            nb_words = len(sortedWords)

        self.root = root
        self.nb_words = nb_words
        self.loader = loader

        self.transform_before = transform_before
        self.transform_after = transform_after
        self.transform_true_before = transform_true_before
        self.transform_true_after = transform_true_after
        
        self.sortedWords = sortedWords
        self.indices = indices

        length = 0
        for i, w1 in enumerate(sortedWords[:nb_words]):
            for j, w2 in enumerate(sortedWords[:nb_words]):
                length += len(indices[w1]) * len(indices[w2])
        
        self.length = length + length // true_period
        self.true_period = true_period

    def get_indices_false(self, index):
        counter = 0
        for i, w1 in enumerate(self.sortedWords[:self.nb_words]):
            for j, w2 in enumerate(self.sortedWords[:self.nb_words]):
                if counter + len(self.indices[w1]) * len(self.indices[w2]) <= index:
                    counter += len(self.indices[w1]) * len(self.indices[w2])
                    continue
                else:
                    a = (index - counter) // len(self.indices[w2])
                    b = (index - counter) % len(self.indices[w2])
                    return self.indices[w1][a], self.indices[w2][b]
    
    def get_indices_true(self, index):
        counter = 0
        for i, w in enumerate(self.sortedWords):
            if counter + len(self.indices[w]) * (len(self.indices[w]) - 1) <= index:
                counter += len(self.indices[w]) * (len(self.indices[w]) - 1)
                continue
            elif len(self.indices[w]) <= 1:
                continue
            else:
                a = (index - counter) // (len(self.indices[w]) - 1)
                b = (index - counter) % (len(self.indices[w]) - 1)
                if b >= a:
                    b += 1
                return self.indices[w][a], self.indices[w][b]
        return self.get_indices_true(index - counter)

    def get_file(self, id):
        return os.path.join(self.root, "word-{:06d}.png".format(id))

    def __getitem__(self, index):
        if index % self.true_period == 0:
            indexA, indexB = self.get_indices_true(index // self.true_period)
            target = 1
        else:
            indexA, indexB = self.get_indices_false(index - index // self.true_period)
            target = 0
        fname_i, fname_j = self.get_file(indexA), self.get_file(indexB)
        sample1, sample2 = self.loader(fname_i), self.loader(fname_j)
        indices = torch.tensor([indexA, indexB], dtype=torch.int)

        if self.transform_before is not None:
            sample1 = self.transform_before(sample1)
            sample2 = self.transform_before(sample2)

        if self.transform_true_before is not None and target == 1:
            sample1 = self.transform_true_before(sample1)
            sample2 = self.transform_true_before(sample2)

        sample1 = transforms.ToTensor()(sample1)
        sample2 = transforms.ToTensor()(sample2)
        sample = torch.cat((sample1, sample2), 0)

        if self.transform_after is not None:
            sample = self.transform_after(sample)

        if self.transform_true_after is not None and target == 1:
            sample = self.transform_true_after(sample)

        return (sample, target, indices)

    def __len__(self):
        return self.length

class WordPairPickle(data.Dataset):

    def __init__(self, root, fileName, loader=grey_pil_loader, 
                transform_before=None, 
                transform_after=None,
                transform_true_before=None,
                transform_true_after=None,
                jump_equal=True, verbose=1, lim=None):
        self.root = root
        self.fileName = os.path.join(root, fileName)
        self.loader = loader
        self.transform_before = transform_before
        self.transform_after = transform_after
        self.transform_true_before = transform_true_before
        self.transform_true_after = transform_true_after

        data = []

        with open(self.fileName, "rb") as f:
            data = pk.load(f)
        
        if lim is not None:
            self.data = data[:lim]
        else:
            self.data = data

    def __getitem__(self, index):
        (a, b), target = self.data[index]
        indexA, indexB = int(a[-10:-4]) - 1, int(b[-10:-4]) - 1
        sample1, sample2 = self.loader(a), self.loader(b)
        indices = torch.tensor([indexA, indexB], dtype=torch.int)

        if self.transform_before is not None:
            sample1 = self.transform_before(sample1)
            sample2 = self.transform_before(sample2)

        if self.transform_true_before is not None and target == 1:
            sample1 = self.transform_true_before(sample1)
            sample2 = self.transform_true_before(sample2)

        sample1 = transforms.ToTensor()(sample1)
        sample2 = transforms.ToTensor()(sample2)
        sample = torch.cat((sample1, sample2), 0)

        if self.transform_after is not None:
            sample = self.transform_after(sample)

        if self.transform_true_after is not None and target == 1:
            sample = self.transform_true_after(sample)

        return (sample, target, indices)
        
    def __len__(self):
        return len(self.data)
