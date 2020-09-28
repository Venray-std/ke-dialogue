# Learning Knowledge Bases with Parameters for Task-Oriented Dialogue Systems
<img src="plot/pytorch-logo-dark.png" width="10%"> [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) 

<img align="right" src="plot/HKUST.jpg" width="12%">

This is the implementation of the paper:

**Learning Knowledge Bases with Parameters for Task-Oriented Dialogue Systems**. [**Andrea Madotto**](https://andreamad8.github.io), Samuel Cahyawijaya, Genta Indra Winata, Yan Xu, Zihan Liu, [Zhaojiang Lin](https://zlinao.github.io/), Pascale Fung **Findings of EMNLP 2020** [[PDF]](TBC)

If you use any source codes or datasets included in this toolkit in your work, please cite the following paper. The bibtex is listed below:
<pre>
TBC
</pre>

## Abstract
Task-oriented dialogue systems are either modularized with separate dialogue state tracking (DST) and management steps or end-to-end trainable. In either case, the knowledge base (KB) plays an essential role in fulfilling user requests. Modularized systems rely on DST to interact with the KB, which is expensive in terms of annotation and inference time. End-to-end systems use the KB directly as input, but they cannot scale when the KB is larger than a few hundred entries. In this paper, we propose a method to embed the KB, of any size, directly into the model parameters. The resulting model does not require any DST or template responses, nor the KB as input, and it can dynamically update its KB via finetuning. We evaluate our solution in five taskoriented dialogue datasets with small, medium, and large KB size. Our experiments show that end-to-end models can effectively embed knowledge bases in their parameters and achieve competitive performance in all evaluated datasets.

## Versatile Generative Language Model (VLM):
<p align="center">
<img src="plot/main.png" width="40%" />
</p>
During training, the KE dialogues are generated by fulfilling the \texttt{TEMPLATE} with the \textit{user goal query} results, and they are used to embed the KB into the model parameter $\theta$. At testing time, the model does not use any external knowledge to generate the correct responses.

## Dependency
Check the packages needed or simply run the command
```console
❱❱❱ pip install -r requirements.txt
```

## Acknowledgement
This repository is implemented base on [**Huggingface**](https://github.com/huggingface/transfer-learning-conv-ai)




