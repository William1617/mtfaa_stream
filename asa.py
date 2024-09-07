"""
Axial Soft Attention (ASA).
NOTE I recommend that you remove the t-attention and only keep
the f-attention when using it, because there is already TFCMs
to time-modeling, and doing so can greatly increase the batch size.

shmzhang@aslp-npu.org, 2022
"""

import einops
import torch as th
import torch.nn as nn


def max_neg_value(t):
    return -th.finfo(t.dtype).max
def creat_mask(size:int,chunk_num,device: th.device = th.device("cpu")):
    ret = th.ones(size, size, device=device, dtype=th.bool)
    for i in range(size):
      
        start = max((i  - chunk_num), 0)
        ending = min((i + 1), size)
        ret[i, start:ending] = False
    return ret


class ASA(nn.Module):
    def __init__(self, c=64):
        super(ASA, self).__init__()
        self.d_c = c//4
        self.f_qkv = nn.Sequential(
            nn.Conv2d(c, self.d_c*3, kernel_size=(1, 1),bias=False),
            nn.BatchNorm2d(self.d_c*3),
            nn.PReLU(self.d_c*3),
        )
        self.t_qk = nn.Sequential(
            nn.Conv2d(c, self.d_c*2, kernel_size=(1, 1),bias=False),
            nn.BatchNorm2d(self.d_c*2),
            nn.PReLU(self.d_c*2),
        )
        self.proj = nn.Sequential(
            nn.Conv2d(self.d_c, c,kernel_size=(1, 1),  bias=False),
            nn.BatchNorm2d(c),
            nn.PReLU(c),
        )
        
    def forward(self, inp,mask):
        """
        inp: B C F T
        """
        # f-attention
        f_qkv = self.f_qkv(inp)
        qf, kf, v = tuple(einops.rearrange(
            f_qkv, "b (c k) f t->k b c f t", k=3))
        
        f_score = th.einsum("bcft,bcyt->btfy", qf, kf) / (self.d_c**0.5)

        f_score = f_score.softmax(dim=-1)
        f_out = th.einsum('btfy,bcyt->bcft', [f_score, v])
        # t-attention
        t_qk = self.t_qk(inp)
        qt, kt = tuple(einops.rearrange(t_qk, "b (c k) f t->k b c f t", k=2))
        
        t_score = th.einsum('bcft,bcfy->bfty', [qt, kt]) / (self.d_c**0.5)
        mask_value = max_neg_value(t_score)   
           
        t_score.masked_fill_(mask, mask_value)
        t_score = t_score.softmax(dim=-1)
        t_out = th.einsum('bfty,bcfy->bcft', [t_score, f_out])
        out = self.proj(t_out)
        return out + inp


def test_asa():
    nnet = ASA(c=64)
    inp = th.randn(2, 64, 4, 10)
    mask=creat_mask(10,4)
    out = nnet(inp,mask)
    print('out: ', out.shape)


if __name__ == "__main__":
    test_asa()
  #  print(creat_mask(100,64))
