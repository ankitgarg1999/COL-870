# -*- coding: utf-8 -*-
"""run_solver.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1bp5th4-CqWco85b1GWkOznbZBZsBkUnq
"""

import sys 
import os


path_train  = str(sys.argv[1])
path_test   = str(sys.argv[2])
path_sample  = str(sys.argv[3])
out_labels  = str(sys.argv[4])

import   numpy as np
import   matplotlib.pyplot as plt
from     PIL import Image
import   cv2
import   torch
import   torch.nn as nn
import   torch.nn.functional as F
import   torch.optim as optim
from     torch.utils.data.sampler import SubsetRandomSampler
from     torch.utils.data import Dataset, DataLoader, TensorDataset
from     torchvision import datasets, transforms
import   imageio
import   copy
import   csv

def one_hot_encode(labels):
  labels_one_hot = np.zeros((labels.shape[0],9), dtype=np.float32)
  for i in range(labels.shape[0]):
    labels_one_hot[i][int(labels[i][0])] = 1
  return labels_one_hot 
def plot_image(image):
  plt.imshow(image, cmap='gray', vmin=np.amin(image), vmax=np.amax(image))
  plt.show()
#######################
# GAN

#################


class generator(nn.Module):

  def __init__(self):

    super(generator, self).__init__()

    self.linear1_z = nn.Linear(100, 200)
    self.linear1_y = nn.Linear(9,1000)

    self.dropZ = nn.Dropout()
    self.dropY = nn.Dropout()

    self.linear2_comb = nn.Linear(1200,1200)
    self.dropZY = nn.Dropout()

    self.linear3 = nn.Linear(1200,784)

  def forward(self, z, y):

    z = F.leaky_relu( self.dropZ(self.linear1_z(z)), negative_slope=0.2)
    y = F.leaky_relu( self.dropY(self.linear1_y(y)), negative_slope=0.2)

    zy = torch.cat((z, y), 1 )
    zy = F.leaky_relu(self.dropZY(self.linear2_comb(zy)), negative_slope=0.2)

    z = self.linear3(zy)
    z = torch.sigmoid(z)

    return z

G = torch.load('./generator.pth')
G.eval()

y = [[0, 0, 0, 0, 0, 0, 0, 0, 0]]

generated_labelled_data = np.zeros((45000,784))
labels = np.zeros((45000,1))

with torch.no_grad():    
  for i in range(0, 9):
    for j in range(0, 5000):

      x = copy.deepcopy(y)
      x[0][i] = 1
      
      x = (torch.tensor(x).float()).cuda()
      z = (torch.randn(1, 100).cuda()).float()
      output = ((G(z,x)[0]).cpu()).detach().numpy()
      generated_labelled_data[i*5000 + j] = output
      labels[i*5000 + j] = i

# np.save(out_images, generated_labelled_data)
# np.save(out_labels, labels)


# X = np.load('./gen9k.npy')
# Y = one_hot_encode(np.load('./target9k.npy'))

X = generated_labelled_data
Y = one_hot_encode(labels)

indices = np.arange(len(X))
np.random.shuffle(indices)
X = X[indices]
Y = Y[indices]

X = X.reshape(-1, 1, 28, 28)

class MyDataset (Dataset):

  def __init__(self, X, Y):
    self.X = X
    self.Y = Y

  def __len__(self):
    return (self.X).shape[0]

  def __getitem__(self, idx):
    return torch.from_numpy(self.X[idx]), torch.from_numpy(self.Y[idx])


b_size = 128

split = int(X.shape[0]*0.8)
neg_split = X.shape[0] - split

train_dataset = MyDataset(X[:split,:],Y[:split,:])
val_dataset = MyDataset(X[split:,:],Y[split:,:])
train_loader = DataLoader(train_dataset, batch_size = b_size, shuffle=False)
val_loader = DataLoader(val_dataset, batch_size = b_size, shuffle=False)

class augment(Dataset):

    def __init__(self, data, transform):
        self.data = data
        self.transform = transform

    def __len__(self):
        return len(self.data.shape[0])

    def __getitem__(self, idx):
        item = self.data[idx]
        item = self.transform(item)
        return item

transform = transforms.Compose([
        transforms.ToPILImage(),
        transforms.RandomAffine(40, translate=(0,.25), scale=(1,1.2), shear=None,  fill=255)
        ,transforms.ToTensor()
    ])

class classifier(nn.Module):
 
  def __init__(self):
 
    super(classifier, self).__init__()
    
    self.conv1 = nn.Conv2d(1, 32, 3)
    self.pool1 = nn.MaxPool2d(2, stride= 2)
 
    self.conv2 = nn.Conv2d(32, 64, 3)
    self.pool2 = nn.MaxPool2d(2, stride= 2)
 
    self.linear1 = nn.Linear(25*64, 128)
    self.linear2 = nn.Linear(128, 9)
 
  def forward(self, x):
 
    x = F.relu(self.conv1(x))
    x = self.pool1(x)
    x = F.relu(self.conv2(x))
    x = self.pool2(x)
 
    x = x.view(-1, 25*64)
    x = F.relu(self.linear1(x))
    x = self.linear2(x)
    # x = F.softmax(x, dim = 1)
    return torch.softmax(x, dim = 1)


neural_net = classifier()
neural_net = neural_net.cuda()

optm = optim.SGD(neural_net.parameters(), lr = 1e-2, momentum = 0.9, weight_decay= 0.0001)

n_epochs = 5


for epoch in range(n_epochs):
  
  neural_net.train()

  ll = 0

  for data in train_loader: 

    x = (augment(data[0], transform).data).cuda().float()
    # x = (data[0].cuda()).float()
    y = (data[1].cuda()).float()

    optm.zero_grad()

    pred = neural_net(x)

    loss = -(torch.log(pred.masked_select(y.ge(0.5)))).mean() 
    loss.backward()

    ll += (loss.item())*b_size

    optm.step()
    torch.cuda.empty_cache()

  loss_t = ll / (split)

  neural_net.eval()

  ll_val = 0 

  if ((epoch+1)%1 == 0):
    torch.save(neural_net, './classifier.pth')

    for data in val_loader:
      with torch.no_grad():

        x = (data[0].cuda()).float()
        y = (data[1].cuda()).float()

        pred = neural_net(x)
        loss = -(torch.log(pred.masked_select(y.ge(0.5)))).mean() 
        ll_val += (loss.item())*b_size

      torch.cuda.empty_cache()

    loss_v = ll_val / (neg_split)

    print("Classifier Epoch : " + str(epoch+1) + " Training Loss: "+ str(loss_t) + " Validation Loss: "+ str(loss_v))

query  = np.load('./query.npy')
target = np.load('./target.npy')

query = query.astype(np.float64)
target= target.astype(np.float64)

b_size = 512
X = np.reshape(query, (-1, 1, 28, 28))
X_t = torch.Tensor(X)
 
p = []
 
test_data   = TensorDataset(X_t) # create your datset
test_loader = DataLoader( test_data, 
                          batch_size=b_size, 
                          shuffle=False)
 
for data in test_loader:
  input = data[0].cuda().float()
  output = neural_net(input)
 
  output = torch.argmax(output, dim=1)
 
  p =  p + output.tolist()
  
p = np.array(p).reshape(-1,1)

p = p.astype(int)
# print(p.shape)
np.save('./labels_gan.npy',p)


b_size = 512
X = np.reshape(target, (-1, 1, 28, 28))
X_t = torch.Tensor(X)
 
p = []
 
test_data   = TensorDataset(X_t) # create your datset
test_loader = DataLoader( test_data, 
                          batch_size=b_size, 
                          shuffle=False)
 
for data in test_loader:
  input = data[0].cuda().float()
  output = neural_net(input)
 
  output = torch.argmax(output[:,1:], dim=1) + 1
 
  p =  p + output.tolist()
  
p = np.array(p).reshape(-1,1)

p = p.astype(int)
np.save('./tlabels_gan.npy',p)

class MyDataset2 (Dataset):

  def __init__(self, X, Y, R, C):
    self.X = X
    self.Y = Y
    self.R = R
    self.C = C

  def __len__(self):
    return (self.X).shape[0]

  def __getitem__(self, idx):
    return torch.from_numpy(self.X[idx]), torch.from_numpy(self.Y[idx]), torch.from_numpy(self.R[idx]), torch.from_numpy(self.C[idx])

class MyDataset3 (Dataset):

  def __init__(self, X,R, C):
    self.X = X
    # self.Y = Y
    self.R = R
    self.C = C

  def __len__(self):
    return (self.X).shape[0]

  def __getitem__(self, idx):
    return torch.from_numpy(self.X[idx]), torch.from_numpy(self.R[idx]), torch.from_numpy(self.C[idx])


input = np.load("./labels_gan.npy")
label = np.load("./tlabels_gan.npy")

input = np.reshape(input, (-1,64))
label = np.reshape(label, (-1,64))

row =  np.array([0,1,2,3,4,5,6,7])
rows = np.tile(np.tile(row, 8), (input.shape[0],1))

col =  np.array([0,1,2,3,4,5,6,7])
cols = np.tile(np.repeat(col , 8), (input.shape[0], 1))

# input = one_hot_encode(input)
# label = one_hot_encode(label)

split    = int((input.shape[0])*0.5)
neg_spit = input.shape[0] - split 

b_size = 16
train_dataset     = MyDataset2(input[:split,:],label[:split,:],rows[:split, :], cols[:split, :])
val_dataset       = MyDataset2(input[split:,:],label[split:,:],rows[split:, :], cols[split:, :])
train_loader      = DataLoader(train_dataset, batch_size = b_size, shuffle=True)
val_loader        = DataLoader(val_dataset, batch_size = b_size, shuffle=False)
train_loader_pred = DataLoader(train_dataset, batch_size = b_size, shuffle=False)

class MLP(nn.Module):

  def __init__(self, size):

    super(MLP, self).__init__()

    self.linear1 = nn.Linear(size, 96)
    self.linear2 = nn.Linear(96, 96)
    # self.linear3 = nn.Linear(96, 96)
    self.linear4 = nn.Linear(96, 96)

    # self.dropZ = nn.Dropout()
    
  def forward(self, x):

    x = F.relu(self.linear1(x))
    x = F.relu(self.linear2(x))
    # x = F.relu(self.linear3(x))
    x = self.linear4(x)
    
    return x

class embedx(nn.Module):

  def __init__(self):

    super(embedx, self).__init__()

    self.emb_input  = nn.Embedding(9, 16)
    self.emb_row    = nn.Embedding(8, 16)
    self.emb_col    = nn.Embedding(8, 16)
    # self.MLP = MLP(48)
    self.MLP = MLP(16)
    
  def forward(self, x, r, c):

    x = self.emb_input(x)
    r = self.emb_row(r)
    c = self.emb_col(c)

    # conc = torch.cat((x, r, c), dim = 2 )

    # out = self.MLP(conc)
    out = self.MLP(x)
    return out

class msg_fn(nn.Module):

  def __init__(self):

    super(msg_fn, self).__init__()
   
    self.MLP = MLP(96*2)
    
  def forward(self, hi, hj):

    conc = torch.cat((hi, hj), dim = 2) # unidirectional message from node i to node j
    out = self.MLP(conc)
    return out  

class node_fn(nn.Module): # Effective LSTM Cell

  def __init__(self):

    super(node_fn, self).__init__()

    self.LSTMG = nn.LSTMCell(96,96)
    self.MLP = MLP(96*2)
    
  def forward(self, x, mt, st_1, ht_1):

    conc = torch.cat((x, mt), dim = 2)
    out = self.MLP(conc)
    
    out = torch.reshape(out, (-1, out.shape[2]))
    st_1 = torch.reshape(st_1, (-1, st_1.shape[2]))
    ht_1 = torch.reshape(ht_1, (-1, ht_1.shape[2]))

    ht, st = self.LSTMG(out, (ht_1, st_1))

    ht = torch.reshape(ht, x.shape)
    st = torch.reshape(st, x.shape)
    return ht, st 

class out_layer(nn.Module):

  def __init__(self):

    super(out_layer, self).__init__()
    self.linear = nn.Linear(96, 8)
  
  def forward(self, x):

    x = self.linear(x)
    return torch.softmax(x, dim=2)
########################################
  # hx size = (batch_size, 64, 96)
  # sx size = (batch_size, 64, 96)
  # x  size = (batch_size, 64, 96)
  # msg_matrix = (batch_size, 64, 64, 96)

class RRN(nn.Module):

  def __init__(self):

    super(RRN, self).__init__()
    
    self.emb    = embedx() # embedding of x, r, c
    self.msf    = msg_fn() # Message from cell i to cell j
    self.nf     = node_fn() # LSTM cell
    self.ol     = out_layer() # maps hidden layer to output layer
    self.b_size = 16


    ## create mask ######
    self.mask = torch.zeros(64,self.b_size, 64, 96).cuda() # (64, batch size, 64, feature size)

    for i in range(64):
      indices = []

      column = int(i/8) 
      indices = indices + [ (8*column + j) for j in range(8) ]
      indices = indices + [ ( i + 8*j) for j in range(-column, 8 - column) ]

      even = (i%2 == 0)
      left = (column < 4)

      if (even and left):
        start = i - 8*column
        indices = indices + [ (start + 8*j) for j in range(4)]
        indices = indices + [ (start + 8*j + 1) for j in range(4)]

      elif ((not even) and left):
        start = i - 8*column
        indices = indices + [ (start + 8*j) for j in range(4)]
        indices = indices + [ (start + 8*j - 1) for j in range(4)]
        

      elif ((not even) and (not left)):
        start = i - 8*(column -4)
        indices = indices + [ (start + 8*j) for j in range(4)]
        indices = indices + [ (start + 8*j - 1) for j in range(4)]        

      elif (even and (not left)):
        start = i - 8*(column -4)
        indices = indices + [ (start + 8*j) for j in range(4)]
        indices = indices + [ (start + 8*j + 1) for j in range(4)]
      
      
      indices = list(set(indices))

      for ind in indices:
        self.mask[i,:, ind,:] = 1

    
  def forward(self, x, r, c, hx, sx, time_step):
    
    x = self.emb(x, r, c)

    if (time_step ==0):
      hx = x
      
    h1 = torch.tile(hx, (1,64, 1))
    h2 = torch.repeat_interleave(hx, 64, dim=1)

    msg_matrix = self.msf(h1, h2)
    sub_matrix = torch.tensor_split(msg_matrix, 64, dim = 1)

    ls = []
    
    # print(sub_matrix[0].shape, self.mask.shape)
    
    for count, sm in enumerate(sub_matrix):
      ls.append(torch.reshape(torch.sum(sm * self.mask[count, :,:,:],1 ), (sm.shape[0], 1, sm.shape[2])))
    
    msg_matrix = torch.cat(ls, dim=1)

    ht, st = self.nf(x, msg_matrix ,sx, hx)

    pred = self.ol(ht)
    return ht, st , pred

n_epochs = 10
n_steps = 30

neural_net = RRN()
neural_net = neural_net.cuda()
neural_net.b_size = b_size


optm = optim.Adam(neural_net.parameters(), lr = 2e-4, weight_decay= 0.0001) 
min_loss = 100

lmbda = lambda epoch: 0.94
scheduler = torch.optim.lr_scheduler.MultiplicativeLR(optm, lr_lambda=lmbda)

for epoch in range(n_epochs):
  loss_t = 0 
  
  neural_net.train()
  for data in train_loader: 
    
    X = data[0].cuda()
    Y = data[1].cuda()
    R = data[2].cuda()
    C = data[3].cuda()

    hx = torch.zeros(X.shape[0], X.shape[1], 96).cuda()
    sx = torch.zeros(X.shape[0], X.shape[1], 96).cuda()
    
    # print(X.shape, Y.shape, R.shape, C.shape)
    
    optm.zero_grad()

    h = []
    s = []
    p = []
    h.append(hx)
    s.append(sx)

    for step in range(n_steps):
      ht, st, pred = neural_net.forward(X, R, C, h[-1], s[-1], step) # time_steps * batch_size * 64 * 96 
      h.append(ht)
      s.append(st)
      p.append(pred)

    ll = 0

    for step in range(n_steps):
      ll += -(torch.log(torch.gather(p[step], 2, (Y - 1).unsqueeze(-1)))).sum()

    ll.backward()
    loss_t += (ll.item()*b_size)   

    optm.step()
    torch.cuda.empty_cache()

  loss_t = loss_t / (split*n_steps*64)
  scheduler.step()

######## Validation

  loss_v = 0
  neural_net.eval()

  with torch.no_grad():

    for val_data in val_loader:

      X = val_data[0].cuda()
      Y = val_data[1].cuda()
      R = val_data[2].cuda()
      C = val_data[3].cuda()

      hx = torch.zeros(X.shape[0], X.shape[1], 96).cuda()
      sx = torch.zeros(X.shape[0], X.shape[1], 96).cuda()
      pred = None

      for step in range(n_steps):
        hx, sx, pred = neural_net.forward(X, R, C, hx, sx, step)

      ll = -(torch.log(torch.gather(pred, 2, (Y - 1).unsqueeze(-1)))).sum()

      loss_v += (ll.item()*b_size)
      torch.cuda.empty_cache()
  
  loss_v = loss_v / (neg_split*64)

  if ((epoch+1)%1 == 0):
    print("RRN Epoch: " + str(epoch+1) + " Training Loss = "+str(loss_t) + " Val Loss = "+ str(loss_v))
  
  torch.save(neural_net, './RRN.pth') # Change path later 

train_img_path  = path_test
num_images      = len(os.listdir(train_img_path))

digit_collection = []

for i in range(num_images): 
  img = Image.open( path_test + '/' + str(i)+'.png')
  img = np.asarray(img) 
  h_tiles = np.hsplit(img, 8)
  for tile in h_tiles:
    digit_collection = digit_collection + np.vsplit(tile, 8)
X_train = (np.stack(digit_collection))/255.0 #Normalise
# X_train = X_train.astype(np.int8)
np.save("./test", X_train.astype(np.int8))


cl = torch.load('./classifier.pth')
cl = cl.cuda()

b_size = 512
X = np.reshape(X_train, (-1, 1, 28, 28))
X_t = torch.Tensor(X)
 
p = []
 
test_data   = TensorDataset(X_t) # create your datset
test_loader = DataLoader( test_data, 
                          batch_size=b_size, 
                          shuffle=False)
 
for data in test_loader:
  input = data[0].cuda().float()
  output = cl(input)
 
  output = torch.argmax(output, dim=1)
 
  p =  p + output.tolist()
  
p = np.array(p).reshape(-1,1)

p = p.astype(np.int)
# print(p.shape)
np.save('./test_labels_gan.npy',p)


input = p


num_images = int(input.shape[0]/64)

input = np.reshape(input, (-1,64))


if(input.shape[0]%16 != 0):
    temp = np.zeros((input.shape[0] + 16 - input.shape[0]%16, input.shape[1]))
    temp[:input.shape[0],:] = input 
    input= temp 

input = input.astype(np.int)

row =  np.array([0,1,2,3,4,5,6,7])
rows = np.tile(np.tile(row, 8), (input.shape[0],1))

col =  np.array([0,1,2,3,4,5,6,7])
cols = np.tile(np.repeat(col , 8), (input.shape[0], 1))

b_size = 16
test_dataset = MyDataset3(input[:,:],rows[:, :], cols[:, :])
test_loader = DataLoader(test_dataset, batch_size = b_size, shuffle=False)

def get_labels(data_loader, neural_net):

  predl = []

  with torch.no_grad():
    for data in data_loader:

        X = data[0].cuda()
        R = data[1].cuda()
        C = data[2].cuda()

        hx = torch.zeros(X.shape[0], X.shape[1], 96).cuda()
        sx = torch.zeros(X.shape[0], X.shape[1], 96).cuda()
        pred = None

        for step in range(30):
          hx, sx, pred = neural_net.forward(X, R, C, hx, sx, step)

        for i in range(0, X.shape[0]):
          pred_labels = (torch.argmax(pred[i], dim = 1)).int()
          pred_labels += 1 
          predl.append(pred_labels.view(-1))
  
  return predl

pred =  get_labels(test_loader, neural_net)

with open(out_labels, 'w') as file:
  writer = csv.writer(file)
  for i in range(num_images):
    writer.writerow([ (str(i)+".png")] + pred[i].tolist())