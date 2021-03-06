# -*- coding: utf-8 -*-
"""test_ner.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1728CApr0908z9bMLWBIb2Xf8Bnt_XNV6
"""

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset
from torch.nn.utils.rnn import pad_sequence, pack_padded_sequence
import torch.optim as optim
import torch.nn.functional as F
from torch.nn.utils import clip_grad_norm_
import math
import sys, getopt
import random

device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")



############ Data Read ################

# Reads the file, extract sentences as a dictionary and append to a list 

def data_read(filename): 

  file = open(filename, 'r')
  raw_data = file.readlines()

  dataset = []
  prev = 0

  for i in range (1,len(raw_data)):

    if (raw_data[i][0] == '\n'):

      data_list = raw_data[prev+1:i]
      data_dict = {}

      sen = []
      pos = []
      act = []
      ent = []

      for j in range(0,len(data_list)):
        temp = data_list[j].split(" ")
        sen.append(temp[0])
        pos.append(temp[1])
        act.append(temp[2])
        ent.append(temp[3][:-1])

      data_dict['sen'] = sen 
      data_dict['pos'] = pos
      data_dict['act'] = act 
      data_dict['ent'] = ent

      dataset.append(data_dict)

      prev = i

  return dataset

# Take the sentences and start indexing every new word ecountered 
# ind 0 is for PAD and 1 is for UNK 

def build_vocab (vocab_file):

  with open(vocab_file, 'r') as f:
    
    raw_data = f.readlines()

    prev = 0
    count = 0

    stoi_ftr_l = {}
    stoi_char_l = {}
    stoi_ent_l = {}

    for i in range (1,len(raw_data)):

      if (raw_data[i] == '\n'):
        count += 1
        data_list = raw_data[prev+1:i]

        if (count == 1):
          for words in data_list:
            stoi_ftr_l[words[:-1]] = len(stoi_ftr_l)

        if (count == 2):
          for words in data_list:
            stoi_char_l[words[:-1]] = len(stoi_char_l)

        if (count == 3):
          for words in data_list:
            stoi_ent_l[words[:-1]] = len(stoi_ent_l)

        prev = i
    rev_label = {v: k for k, v in stoi_ent_l.items()}

  return stoi_ftr_l, rev_label, stoi_char_l


# take the dataset i.e. list of dictionaries and convert each dictionary/sentence to a list with 
# token replaced by vocab index 

def stoi_data(dataset, stoi_ftr, stoi_char):
  X   = []
  XC  = []

  for data in dataset:
    sentence = []
    sent_c = []

    for word in data['sen']:
      word_c = []
      if word in stoi_ftr.keys():
        sentence.append(stoi_ftr[word])
      else:
        sentence.append(stoi_ftr['<UNK>'])

      for char in word: 
        if char in stoi_char.keys():
          word_c.append(stoi_char[char])
        else:
          word_c.append(stoi_char['<UNK>'])
      sent_c.append(word_c)

    X.append(sentence)
    XC.append(sent_c)

  return X,XC

def get_data(data_file, vocab_file):

  test_data   = data_read(data_file)

  stoi_ftr, rev_label, stoi_char = build_vocab(vocab_file)
  
  X_test, XC_test = stoi_data(test_data, stoi_ftr, stoi_char)

  return X_test, XC_test, test_data, rev_label
################################################################

## Models

#### Implementation of lstm with layer normalization

class MyLstmCell (nn.Module):

  def __init__ (self, input_size, hidden_size):

    super(MyLstmCell, self).__init__()

    self.hidden_size = hidden_size 
    self.input_size = input_size 

    self.weight_ii = nn.Parameter(((torch.rand([hidden_size, input_size], dtype=torch.float))*2 - 1)/math.sqrt(hidden_size), requires_grad = True)
    self.bias_ii = nn.Parameter(((torch.rand([hidden_size], dtype=torch.float))*2 - 1)/math.sqrt(hidden_size), requires_grad = True)
    self.weight_if = nn.Parameter(((torch.rand([hidden_size, input_size], dtype=torch.float))*2 - 1)/math.sqrt(hidden_size), requires_grad = True)
    self.bias_if = nn.Parameter(((torch.rand([hidden_size], dtype=torch.float))*2 - 1)/math.sqrt(hidden_size), requires_grad = True)
    self.weight_ig = nn.Parameter(((torch.rand([hidden_size, input_size], dtype=torch.float))*2 - 1)/math.sqrt(hidden_size), requires_grad = True)
    self.bias_ig = nn.Parameter(((torch.rand([hidden_size], dtype=torch.float))*2 - 1)/math.sqrt(hidden_size), requires_grad = True)
    self.weight_io = nn.Parameter(((torch.rand([hidden_size, input_size], dtype=torch.float))*2 - 1)/math.sqrt(hidden_size), requires_grad = True)
    self.bias_io = nn.Parameter(((torch.rand([hidden_size], dtype=torch.float))*2 - 1)/math.sqrt(hidden_size), requires_grad = True)

    self.weight_hi = nn.Parameter(((torch.rand([hidden_size, hidden_size], dtype=torch.float))*2 - 1)/math.sqrt(hidden_size), requires_grad = True)
    self.bias_hi = nn.Parameter(((torch.rand([hidden_size], dtype=torch.float))*2 - 1)/math.sqrt(hidden_size), requires_grad = True)
    self.weight_hf = nn.Parameter(((torch.rand([hidden_size, hidden_size], dtype=torch.float))*2 - 1)/math.sqrt(hidden_size), requires_grad = True)
    self.bias_hf = nn.Parameter(((torch.rand([hidden_size], dtype=torch.float))*2 - 1)/math.sqrt(hidden_size), requires_grad = True)
    self.weight_hg = nn.Parameter(((torch.rand([hidden_size, hidden_size], dtype=torch.float))*2 - 1)/math.sqrt(hidden_size), requires_grad = True)
    self.bias_hg = nn.Parameter(((torch.rand([hidden_size], dtype=torch.float))*2 - 1)/math.sqrt(hidden_size), requires_grad = True)
    self.weight_ho = nn.Parameter(((torch.rand([hidden_size, hidden_size], dtype=torch.float))*2 - 1)/math.sqrt(hidden_size), requires_grad = True)
    self.bias_ho = nn.Parameter(((torch.rand([hidden_size], dtype=torch.float))*2 - 1)/math.sqrt(hidden_size), requires_grad = True)

  def forward (self, x, h_o , c_o , ln):

    b_size = x.shape[0]

    h_o = h_o.cuda()
    c_o = c_o.cuda()

    i = torch.sigmoid(torch.matmul(x, torch.transpose(self.weight_ii, 0, 1)) + self.bias_ii 
                      + torch.matmul(h_o, torch.transpose(self.weight_hi, 0, 1)) + self.bias_hi)

    f = torch.sigmoid(torch.matmul(x, torch.transpose(self.weight_if, 0, 1)) + self.bias_if
                      + torch.matmul(h_o, torch.transpose(self.weight_hf, 0, 1)) + self.bias_hf)

    g = torch.tanh(torch.matmul(x, torch.transpose(self.weight_ig, 0, 1)) + self.bias_ig 
                      + torch.matmul(h_o, torch.transpose(self.weight_hg, 0, 1)) + self.bias_hg)

    o = torch.sigmoid(torch.matmul(x, torch.transpose(self.weight_io, 0, 1)) + self.bias_io 
                      + torch.matmul(h_o, torch.transpose(self.weight_ho, 0, 1)) + self.bias_ho)

    c = f * c_o + i * g

    h = o * torch.tanh( ln(c) )

    return h, c

class MyLstm (nn.Module):

  def __init__ (self, input_size, hidden_size):

    super(MyLstm, self).__init__()

    self.input_size = input_size
    self.hidden_size = hidden_size

    self.lstm_f = MyLstmCell(input_size, hidden_size)
    self.lstm_b = MyLstmCell(input_size, hidden_size)

    self.ln = nn.LayerNorm([hidden_size])

  def forward(self, x):

    b_size = x.shape[0]
    T = x.shape[1]

    h_f = [torch.zeros(b_size, self.hidden_size)]
    c_f = [torch.zeros(b_size, self.hidden_size)]

    h_b = [torch.zeros(b_size, self.hidden_size)]
    c_b = [torch.zeros(b_size, self.hidden_size)]

    for t in range(0,T):

      h_f_t, c_f_t = self.lstm_f(x[:, t, :], h_f[-1], c_f[-1], self.ln)
      h_b_t, c_b_t = self.lstm_b(x[:, T-1-t, :], h_b[-1], c_b[-1], self.ln)

      h_f_t = h_f_t.cuda()
      c_f_t = c_f_t.cuda()
      h_b_t = h_b_t.cuda()
      c_b_t = c_b_t.cuda()

      h_f.append(h_f_t)
      c_f.append(h_f_t)

      h_b.append(h_b_t)
      c_b.append(c_b_t)

    h_f = h_f[1:]
    h_b = h_b[1:]

    h_b.reverse()

    output = torch.stack([torch.cat((h_f[i], h_b[i]), dim = 1) for i in range (0,T)], dim = 1)
    return output

class model(nn.Module):

  def __init__(self, vocab_size, char_size, hidden_size, Glove, pre_trained, layer_norm, char_emb ,char_hidden_size = 25):

    super(model, self).__init__()

    self.embedding = None
    self.layer_norm = layer_norm
    self.char_hidden_size = char_hidden_size
    self.char_emb = char_emb


    self.char_embedding = None 
    self.char_lstm = None 

    if (not char_emb):
      self.char_hidden_size = 0 
    else:
      self.char_embedding = nn.Embedding(char_size, char_hidden_size, 0)
      self.char_lstm      = nn.LSTM(input_size = char_hidden_size, hidden_size = char_hidden_size, batch_first = True,bidirectional = True)

    if (pre_trained):
      self.embedding = nn.Embedding.from_pretrained(embeddings = Glove, freeze = False, padding_idx = 0)
    else:
      self.embedding = nn.Embedding(vocab_size, 100, 0)

    self.lstm = None

    if (layer_norm):
      self.lstm = MyLstm(input_size = (100+2*self.char_hidden_size), hidden_size = hidden_size) 

    else:
      self.lstm = nn.LSTM(input_size = (100 + 2*self.char_hidden_size) , hidden_size = hidden_size, batch_first = True,bidirectional = True) 
    
    self.linear = nn.Linear((2*hidden_size),17)

  def forward(self, x, xc):

    x = self.embedding(x)
    if (self.char_emb):
      xc = self.char_embedding(xc)
      shape = xc.shape
      xc = xc.view(-1, shape[2] ,self.char_hidden_size)
      xc = self.char_lstm(xc)

      xc = xc[0].view(shape[0],shape[1],shape[2],-1)
      x = torch.cat((x,xc[:,:,0,self.char_hidden_size:], xc[:,:,-1,0:self.char_hidden_size]), 2)

    x = self.lstm(x)
    y = None

    if (self.layer_norm):
      y  = self.linear(x)
    else:
      y = self.linear(x[0])

    return F.softmax(y, dim = 2)

######### CRF #########

class MyDataset (Dataset):

  def __init__(self, X):
    self.X = X 

  def __len__(self):
    return len(self.X)

  def __getitem__(self, idx):
    return torch.tensor(self.X[idx])

def MyCollate(batch):
  ftr = batch
  ftr_len = [x.shape[0] for x in ftr]
  ftr = nn.utils.rnn.pad_sequence(ftr, batch_first=True, padding_value=0)
  return ftr, ftr_len

class MyCRF(nn.Module):

  def __init__(self, num_labels = 17 ):

    super(MyCRF, self).__init__()

    self.num_labels = num_labels
    A_init = ((torch.rand([num_labels,num_labels],dtype=torch.float))*2 - 1)*0.1 
    self.A = nn.Parameter(A_init, requires_grad = True)
  
  def forward(self, x, y):
    """
    x is scores of sequence - shape [batch_size, sentence_length, num_labels]
    y are the gold labels of the sequence - shape [batch_size, sentence_length]
    Outputs the most likely label sequence
    """
    
    if (self.training):
      mls = self.most_likely_sequence(x, y)
      nll = self.loss(x, y)
      return mls, nll

    else:
      mls = self.most_likely_sequence(x, y)
      return mls

  def most_likely_sequence(self, x, y):
    """
    Viterbi decoding algorithm
    """

    with torch.no_grad():

      batch_pred = []
      batch_len, seq_len, num_labels = x.shape 
      mask = None

      if (self.training):
        mask = (y >= 0).float() # [batch_size, seq_len] 
      else:
        mask = torch.zeros([batch_len, seq_len])
        for i in range(0, batch_len):
          mask[i, :y[i]] = 1 

      lengths = torch.sum(mask, dim = 1)
      dp = torch.zeros([batch_len, seq_len, num_labels, 2])
      dp = dp - 1e5
      dp = dp.cuda()

      for j in range(0, num_labels):
        dp[:, 0, j, 0] = x[:, 0, j]

      for j in range(1, seq_len):
        for k in range(0, num_labels):
          for l in range(0, num_labels):
            temp = dp[:, j-1, k, 0] + self.A[k][l] + x[:, j, l]
            check = (temp > dp[:, j, l, 0]).float()
            dp[:, j, l, 0] = ((1 - check)*(dp[:, j, l, 0])) + check*temp
            dp[:, j, l, 1] = ((1 - check)*(dp[:, j, l, 1])) + check*k

      for i in range (0, batch_len):
        max_val = -1e6
        max_ind = -1

        length = int(lengths[i])

        for j in range(0, num_labels):
          if (dp[i][length-1][j][0] > max_val):
            max_val = dp[i][length-1][j][0]
            max_ind = j

        pred = []
        pred.append(max_ind)

        for j in range(length-1, 0, -1):
          prev = pred[-1]
          pred.append(int(dp[i][j][prev][1].item()))

        pred.reverse()
        batch_pred.append(pred)

      return batch_pred # A list of lists contataining the prediction

  def partition_function (self, x, y):
    """
    Softmax normalization constant Z
    """
  
    batch_len, seq_len, num_labels = x.shape 
    mask = (y >= 0).float() # [batch_size, seq_len] 
    lengths = torch.sum(mask, dim = 1)

    dp = torch.zeros([batch_len, seq_len, num_labels, num_labels]) # 3rd dimension stores the pre exponential stuff to take log later
    dp = dp.cuda()

    log_alpha = torch.zeros([batch_len, seq_len, num_labels]).cuda()

    for j in range(0, num_labels):#k+1'
      for k in range(0, num_labels):#k'
        dp[:, 0, j, k] =  x[:, 0, k] + self.A[k][j]

    log_alpha[:, 0, :] = torch.logsumexp(dp[:, 0,: , :].clone(), 2)

    for j in range(1, seq_len-1): # word i.e. k 
      for k in range(0, num_labels):# y(k'+1) 
        for l in range(0, num_labels):# yk' 

          dp[:, j, k, l] =  mask[:, j]*(x[:, j, l] + log_alpha[:, j-1, l].clone() + self.A[l][k]) + (1 - mask[:, j])*(dp[:, j-1, k, l])

      log_alpha[:, j, :] = torch.logsumexp(dp[:, j, :, :].clone(), 2)

    for l in range(0, num_labels): # inner index i.e. yk'           
      dp[:, -1, 0, l] =  x[:, -1, l] + log_alpha[:, -2, l].clone()

    z = torch.logsumexp(dp[:, -1, 0, :].clone(),1)
    return z

  def loss(self, x, y):
    """
    Calculates loss for the crf model
    This function called only during training time
    """

    batch_len, seq_len, num_labels = x.shape 
    Z = self.partition_function(x, y) ## [batch_size] vector
    
    sum = torch.zeros(batch_len)
    sum = sum.cuda()

    mask = (y >= 0).float() # [batch_size, seq_len] 

    for i in range(0, seq_len):

      x_t = x[:, i] # All the scores at the the i th time step, [batch_size, num_labels]
      p_y_t = x_t[range(batch_len),(y[:, i]).tolist()] # [batch_size] scores corresponding to the correct labels.
      sum = sum + mask[:, i]*p_y_t

      if (i > 0):
        sum = sum + mask[:, i]*(self.A[(y[:, i]).tolist(),(y[:, i-1]).tolist()])

    ll = (- sum + Z).mean()
    return ll

class crf_bilstm(nn.Module):

  def __init__(self, vocab_size, hidden_size):

    super(crf_bilstm, self).__init__()

    self.embedding = nn.Embedding(vocab_size, 100, 0)

    self.lstm = nn.LSTM(input_size = 100, hidden_size = hidden_size, batch_first = True,bidirectional = True) 
    self.linear = nn.Linear((2*hidden_size),17)
    self.crf = MyCRF(num_labels = 17)

  def forward(self, x, label = None):

    x = self.embedding(x)
    x = self.lstm(x)
    y = self.linear(x[0])
    return self.crf(y, label)

    
################################################################ 

##Train Model ############
def test(model, X, XC, output_path, rev_label, data_dict):

  with torch.no_grad():
    for count, sen in enumerate(X):
      input = torch.tensor(sen).cuda()
      input = torch.reshape(input,(1,input.shape[0]))

      input_c = XC[count]
      max_cols = max([len(batch) for batch in input_c ])
      max_rows = len(input_c)
      padded = [ batch + ([0] * (max_cols- len(batch))) for batch in input_c]

      char = torch.tensor(padded).cuda()
      char = torch.reshape(char, (1, char.shape[0], char.shape[1]))
      pred  = model.forward(input, char)

      max_val, max_ind = torch.max(pred, 2)
      lab_pred    = (max_ind.view(-1)).tolist()
      lab_pred_tf = [rev_label[v] for v in lab_pred ]

      original_sen = data_dict[count]

      one   = original_sen['sen']
      two   = original_sen['pos']
      three = original_sen['act']
      
      with open(output_path, 'a') as file:
        for line in range(len(one)):
          file.write("{} {} {} {}\n".format(one[line], two[line], three[line], lab_pred_tf[line]))
        file.write("\n") 

def test_crf(neural_net, X, XC, output_path, rev_label, data_dict):

  test_dataset = MyDataset(X)
  test_loader = DataLoader(test_dataset, batch_size = min(1000, len(X)), shuffle=False, collate_fn=MyCollate)

  global_pred = [] # double list with each list inside list corresponding to a sentence

  with torch.no_grad():
    for data in test_loader:
    
      input = data[0]
      input_len = data[1]
      input = input.cuda()   

      mls = neural_net.forward(input, input_len)

      batch_pred = []

      for sen in mls:
        pred = [rev_label[v] for v in sen]
        batch_pred.append(pred)

      global_pred = global_pred + batch_pred
      torch.cuda.empty_cache()

  for count, lab_pred in enumerate(global_pred):
 
    original_sen = data_dict[count]

    one   = original_sen['sen']
    two   = original_sen['pos']
    three = original_sen['act']
    
    with open(output_path, 'a') as file:
      for line in range(len(one)):
        file.write("{} {} {} {}\n".format(one[line], two[line], three[line], lab_pred[line]))
      file.write("\n") 


################ Parse Command line arguments ##############

use_ce    = False 
use_ln    = False
use_crf   = False

init = ""

test_data_path    = "" 
output_path       = ""
glove_file        = ""
vocab_file        = ""
model_file        = ""

argumentList = sys.argv[1:]
 
# Options
options = ""
 
# Long options
long_options = ["model_file=","char_embeddings=","layer_normalization=","crf=","test_data_file=","output_file=", "glove_embeddings_file=",
                "vocabulary_input_file=", "initialization=" ]
 
try:
    # Parsing argument
    arguments, values = getopt.getopt(argumentList, options, long_options)
     
    # checking each argument
    for currentArgument, currentValue in arguments:
                  
      if currentArgument in ("--test_data_file"):
        test_data_path = currentValue 

      elif currentArgument in ("--initialization"):
        init = currentValue 

      elif currentArgument in ("--output_file"):
        output_path = currentValue

      elif currentArgument in ("--glove_embeddings_file"):
        glove_file = currentValue

      elif currentArgument in ("--vocabulary_input_file"):
        vocab_file = currentValue      
        
      elif currentArgument in ("--model_file"):
        model_file = currentValue

      elif currentArgument in ("--char_embeddings"):
        if(currentValue == '1'):
          use_ce = True 
      
      elif currentArgument in ("--layer_normalization"):
        if(currentValue == '1'):
          use_ln = True 

      elif currentArgument in ("--crf"):
        if(currentValue == '1'):
          use_crf = True
             
except getopt.error as err:
    # output error, and return with an error code
    print (str(err))
  
print(test_data_path, output_path, glove_file, model_file,vocab_file, use_ce, use_ln, use_crf)


if __name__ == "__main__":

  X_test, XC_test, data_dict, rev_label = get_data(test_data_path, vocab_file)

  neural_net = torch.load(model_file)
  neural_net.cuda()
  neural_net.eval()

  if (use_crf):
    test_crf(neural_net , X_test, XC_test, output_path, rev_label, data_dict)
  else:  
    test(neural_net , X_test, XC_test, output_path, rev_label, data_dict)