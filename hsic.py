# -*- coding: utf-8 -*-
"""XIC.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1ozY99QOhKfLSwP54dpSehhJClrCmGcLX
"""
import os
os.environ["CUDA_VISIBLE_DEVICES"] = "4"
import numpy as np
import io
import pandas as pd
import scipy.optimize
import scipy.stats
import matplotlib.pyplot as plt
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, RationalQuadratic, ExpSineSquared
from scipy import sparse
import math
import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.metrics import r2_score


def kernelMatrixGaussian(m, m2, sigma=None, pairwise_distances=None):
    """
    Calculates kernel matrix with a Gaussian kernel

    m: rows are data points
    m2: rows are data points
    sigma: the bandwidth of the Gaussian kernel.
           If not provided, the median distance between points will be used.

    """
    # If sigma is not provided, set sigma based on median distance heuristic.
    if sigma is None:
        sigma = math.sqrt(0.5 * np.median(pairwise_distances[pairwise_distances > 0]))
    gamma = -1.0 / (2 * sigma ** 2)
    return torch.exp(gamma * pairwise_distances)


def HSIC(X, Y, N_samp=100, kernelX="Gaussian", kernelY="Gaussian", sigmaX=None, sigmaY=None):
    #     X = torch.from_numpy(X).double().cuda()
    #     Y = torch.from_numpy(Y).double().cuda()
    m, _ = X.shape
    x_distances = torch.sum(X ** 2, -1).reshape((-1, 1))
    pairwise_distances_x = -2 * torch.mm(X, X.t()) + x_distances + x_distances.t()

    y_distances = torch.sum(Y ** 2, -1).reshape((-1, 1))
    pairwise_distances_y = -2 * torch.mm(Y, Y.t()) + y_distances + y_distances.t()
    # Calculate Gram matrices
    K = kernelMatrixGaussian(X, X, 2.0, pairwise_distances_x) if kernelX == "Gaussian" else kernelMatrixLinear(X, X)
    L = kernelMatrixGaussian(Y, Y, 1.0, pairwise_distances_y) if kernelY == "Gaussian" else kernelMatrixLinear(Y, Y)

    # Centering matrix
    H = torch.eye(m) - 1.0 / m * torch.ones((m, m))
    H = H.double().cuda()

    Kc = torch.mm(H, torch.mm(K, H))

    # Dividing by m here, although some papers use m-1
    HSIC = torch.trace(torch.mm(L, Kc)) / m ** 2
    return HSIC


# X sigma
# x_distances = np.sum(X_train**2,-1).reshape((-1,1))
# pairwise_distances = -2*np.matmul(X_train,X_train.transpose()) + x_distances + x_distances.transpose()
# math.sqrt(0.5 * np.median(pairwise_distances[pairwise_distances>0]))

class Net(nn.Module):
    def __init__(self):
        super(Net, self).__init__()
        self.linear1 = nn.Linear(6, 50, bias=True).double()
        self.linear2 = nn.Linear(50, 50).double()
        self.linear3 = nn.Linear(50, 50).double()
        self.linear4 = nn.Linear(50, 1).double()

    def forward(self, x):
        x = self.linear1(x)
        x = nn.ReLU()(x)
        x = self.linear2(x)
        x = nn.ReLU()(x)
        x = self.linear3(x)
        x = nn.ReLU()(x)
        x = self.linear4(x)
        return x


def training(X, Y, X_test, Y_test, num_iterations=2000, batch_size=32, loss_type='mse'):
    f = Net().cuda()
    X = torch.from_numpy(X).cuda()
    Y = torch.from_numpy(Y).cuda()
    n = X.shape[0]
    if loss_type == 'hsic':
        f_optimizer = optim.Adam(f.parameters(), lr=np.random.uniform(low=0.001,high=0.002))
    elif loss_type == 'mse' or loss_type == 'mae':
        f_optimizer = optim.Adam(f.parameters(), lr=np.random.uniform(low=0.0001, high=0.001))
    scheduler = optim.lr_scheduler.StepLR(f_optimizer, step_size=30, gamma=0.5)
    for i in range(num_iterations):
        batch_idx = np.random.choice(n, batch_size)
        f_optimizer.zero_grad()
        y_pred = f(X[batch_idx])
        #     print(y_pred,Y[batch_idx])
        res = Y[batch_idx] - y_pred
        #     print("res:",res)
        if loss_type=='hsic':
            loss = HSIC(X[batch_idx], res)
        elif loss_type == 'mse':
            #     loss = (torch.abs(res)).mean()
            loss = (res ** 2).mean()
        elif loss_type == 'mae':
            loss = torch.abs(res).mean()
        if i % 100 == 0:
            scheduler.step()
        # print(loss**0.5)
        loss.backward()
        f_optimizer.step()

    # print(torch.cat([y_pred,Y[batch_idx]],dim=1))
    X_test = torch.from_numpy(X_test).cuda()
    X_train = X
    Y_test = torch.from_numpy(Y_test).cuda()
    Y_train = Y
    y_pred = f(X_test) + Y_train.mean() - f(X_train).mean() if loss_type=='hsic' else f(X_test)
    #   print(torch.cat([y_pred,Y_test],dim=1))
    res = Y_test - y_pred
    # f_loss = HSIC(X_test, res)
    f_loss = (res ** 2).mean()

    return f_loss.item() ** 0.5  # ,f(X_test).cpu().detach().numpy()

df = pd.read_csv('auto-mpg.data', header=None, delim_whitespace=True)
col_names = ['mpg', 'cylinders', 'displacement', 'horsepower', 'weight', 'acceleration', 'model year', 'origin',
             'car name']
df.columns = col_names
df = df[df['horsepower'] != '?']

features_list_m1 = ['cylinders', 'displacement', 'horsepower', 'weight', 'acceleration', 'model year', 'origin']
X1 = df[features_list_m1]
y1 = df['mpg']

# X_train, Y_train = np.array(X1[X1['origin'] != 1]).astype(np.double), \
#                    np.array(y1[X1['origin'] != 1]).astype(np.double)
# X_test, Y_test = np.array(X1[X1['origin'] == 1]).astype(np.double), \
#                  np.array(y1[X1['origin'] == 1]).astype(np.double)
# Y_train, Y_test = Y_train.reshape((-1, 1)), Y_test.reshape((-1, 1))
# X_train, X_test = X_train[:, :-1], X_test[:, :-1]

# X1 = np.array(X1).astype(np.double)
# y1 = np.array(y1).astype(np.double).reshape((-1, 1))
# perm = np.random.permutation(X1.shape[0])
# X1, y1 = X1[perm], y1[perm]
# X_train, Y_train = X1[:-128], y1[:-128]
# X_test, Y_test = X1[-128:], y1[-128:]
# X_train, X_test = X_train[:, :-1], X_test[:, :-1]
#
# X_train_mean, X_train_std = X_train.mean(axis=0), X_train.std(axis=0)
# X_train, X_test = (X_train - X_train_mean) / X_train_std, (X_test - X_train_mean) / X_train_std
# Y_train_mean, Y_train_std = Y_train.mean(axis=0), Y_train.std(axis=0)
# Y_train, Y_test = (Y_train - Y_train_mean) / Y_train_std, (Y_test - Y_train_mean) / Y_train_std
#
# mse = [training(X_train, Y_train, X_test, Y_test, hsic=False) for _ in range(50)]
# hsic_loss = [training(X_train, Y_train, X_test, Y_test, hsic=True) for _ in range(50)]
#
# np.save("mse_100", mse)
# np.save("hsic_100", hsic_loss)
# print(np.mean(mse),np.mean(hsic_loss),100)


features_list_m1 = ['cylinders', 'displacement', 'horsepower', 'weight', 'acceleration', 'model year', 'origin']
X1 = df[features_list_m1]
y1 = df['mpg']
for i in [3]:
    X_train, Y_train = np.array(X1[X1['origin'] != i]).astype(np.double), np.array(y1[X1['origin'] != i]).astype(
        np.double)
    X_test, Y_test = np.array(X1[X1['origin'] == i]).astype(np.double), np.array(y1[X1['origin'] == i]).astype(
        np.double)
    Y_train, Y_test = Y_train.reshape((-1, 1)), Y_test.reshape((-1, 1))
    X_train, X_test = X_train[:, :-1], X_test[:, :-1]
    X_train_mean, X_train_std = X_train.mean(axis=0), X_train.std(axis=0)
    X_train, X_test = (X_train - X_train_mean) / X_train_std, (X_test - X_train_mean) / X_train_std
    Y_train_mean, Y_train_std = Y_train.mean(axis=0), Y_train.std(axis=0)
    Y_train, Y_test = (Y_train - Y_train_mean) / Y_train_std, (Y_test - Y_train_mean) / Y_train_std
    mse = [training(X_train, Y_train, X_test, Y_test,num_iterations=900, loss_type='mse') for _ in range(100)]
    mae = [training(X_train, Y_train, X_test, Y_test,num_iterations=900, loss_type='mae') for _ in range(100)]
    hsic_loss = [training(X_train, Y_train, X_test, Y_test, loss_type='hsic') for _ in range(100)]
    np.save("exp/non_linear_32mse1" + str(i), mse)
    np.save("exp/non_linear_32mae1" + str(i), mae)
    np.save("exp/non_linear_32hsic1" + str(i), hsic_loss)
    print(np.mean(mse), np.std(mse))
    print(np.mean(mae), np.std(mae))
    print(np.mean(hsic_loss), np.std(hsic_loss))