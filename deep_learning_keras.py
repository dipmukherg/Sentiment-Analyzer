"""
This example shows how to use an LSTM sentiment classification model trained
using Keras in spaCy. spaCy splits the document into sentences, and each
sentence is classified using the LSTM. The scores for the sentences are then
aggregated to give the document score. This kind of hierarchical model is quite
difficult in "pure" Keras or Tensorflow, but it's very effective. The Keras
example on this dataset performs quite poorly, because it cuts off the documents
so that they're a fixed size. This hurts review accuracy a lot, because people
often summarise their rating in the final sentence
Prerequisites:
spacy download en_vectors_web_lg
pip install keras==2.0.9
Compatible with: spaCy v2.0.0+
"""

import plac
import random
import pathlib
import cytoolz
import numpy
from keras.models import Sequential, model_from_json
from keras.layers import LSTM, Dense, Embedding, Bidirectional
from keras.layers import TimeDistributed
from keras.optimizers import Adam
import thinc.extra.datasets
from spacy.compat import pickle
import spacy
import pandas as pd
import re
import itertools
import numpy as np

class SentimentAnalyser(object):
    @classmethod
    def load(cls, path, nlp, max_length=100):
        with (path / "config.json").open() as file_:
            model = model_from_json(file_.read())
        with (path / "model").open("rb") as file_:
            lstm_weights = pickle.load(file_)
        embeddings = get_embeddings(nlp.vocab)
        model.set_weights([embeddings] + lstm_weights)
        return cls(model, max_length=max_length)

    def __init__(self, model, max_length=100):
        self._model = model
        self.max_length = max_length

    def __call__(self, doc):
        X = get_features([doc], self.max_length)
        y = self._model.predict(X)
        self.set_sentiment(doc, y)

    def pipe(self, docs, batch_size=1000):
        for minibatch in cytoolz.partition_all(batch_size, docs):
            minibatch = list(minibatch)
            sentences = []
            for doc in minibatch:
                sentences.extend(doc.sents)
            Xs = get_features(sentences, self.max_length)
            ys = self._model.predict(Xs)
            for sent, label in zip(sentences, ys):
                sent.doc.sentiment += label - 0.5
            for doc in minibatch:
                yield doc

    def set_sentiment(self, doc, y):
        doc.sentiment = float(y[0])
        # Sentiment has a native slot for a single float.
        # For arbitrary data storage, there's:
        # doc.user_data['my_data'] = y


def get_labelled_sentences(docs, doc_labels):
    labels = []
    sentences = []
    for doc, y in zip(docs, doc_labels):
        for sent in doc.sents:
            sentences.append(sent)
            labels.append(y)
    return sentences, numpy.asarray(labels, dtype="int32")


def get_features(docs, max_length):
    docs = list(docs)
    Xs = numpy.zeros((len(docs), max_length), dtype="int32")
    for i, doc in enumerate(docs):
        j = 0
        for token in doc:
            vector_id = token.vocab.vectors.find(key=token.orth)
            if vector_id >= 0:
                Xs[i, j] = vector_id
            else:
                Xs[i, j] = 0
            j += 1
            if j >= max_length:
                break
    return Xs

def cleanhtml(sentence): #function to clean the word of any html-tags
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, ' ', sentence)
    return cleantext
def cleanpunc(sentence): #function to clean the word of any punctuation or special characters
    cleaned = re.sub(r'[?|%|!|+|*|@|&|^|`|~|\'|"|#|=]',r'',sentence)
    cleaned = re.sub(r'[:|;|.|)|(|,|\|/|_|-]',r' ',cleaned)
    cleaned = re.sub(r'\s+',r' ',cleaned)
    return cleaned

def cleannewline(sentance):
    cleaned = re.sub(r'\n',r' ',sentance)
    return cleaned

def cleannumbers(sentance):
    cleaned=re.sub(r'\s\d*',r' ',sentance)
    return cleaned

def cleanurl(sentance):
    cleaned=re.sub(r'http\S*',r' ',sentance)
    return cleaned

def batch_generator(word_vectors, labels, batch_size,steps_per_epoch):
    idx=0
    while True: 
        yield load_data(word_vectors,labels,idx,batch_size)
        if idx<steps_per_epoch:
            idx+=1
        else:
            idx=0

def load_data(word_vectors,labels,idx,batch_size):
    x = pd.read_csv(word_vectors,skiprows=idx*batch_size,nrows=batch_size)
         
    y = pd.read_csv(labels,skiprows=idx*batch_size,nrows=batch_size)

    return (np.array(x), np.array(y))


def train(
    lstm_shape,
    lstm_settings,
    lstm_optimizer,
    batch_size=100,
    nb_epoch=5,
    by_sentence=True,
):

    print("Loading spaCy")
    nlp = spacy.load("en_vectors_web_lg")
    nlp.add_pipe(nlp.create_pipe("sentencizer"))
    embeddings = get_embeddings(nlp.vocab)
    model = compile_lstm(embeddings, lstm_shape, lstm_settings)

    steps_per_epoch=np.ceil(1119999 / batch_size)
    validation_steps=np.ceil(480000/batch_size)
    my_training_batch_generator = batch_generator('train.csv', 'train_labels.csv', batch_size,steps_per_epoch)
    my_validation_batch_generator = batch_generator('dev.csv', 'dev_labels.csv', batch_size,validation_steps)
    

    # if by_sentence:
    #     train_docs, train_labels = get_labelled_sentences(train_docs, train_labels)
    #     dev_docs, dev_labels = get_labelled_sentences(dev_docs, dev_labels)

    # train_X = get_features(train_docs, lstm_shape["max_length"])
    # dev_X = get_features(dev_docs, lstm_shape["max_length"])
    # model.fit(
    #     train_X,
    #     train_labels,
    #     validation_data=(dev_X, dev_labels),
    #     epochs=nb_epoch,
    #     batch_size=batch_size,
    # )

    model.fit_generator(
        my_training_batch_generator,
        steps_per_epoch=steps_per_epoch,
        validation_data=my_validation_batch_generator,
        validation_steps=validation_steps,
        epochs=nb_epoch,
    )
    return model


def compile_lstm(embeddings, shape, settings):
    model = Sequential()
    model.add(
        Embedding(
            embeddings.shape[0],
            embeddings.shape[1],
            input_length=shape["max_length"],
            trainable=False,
            weights=[embeddings],
            mask_zero=True,
        )
    )
    model.add(TimeDistributed(Dense(shape["nr_hidden"], use_bias=False)))
    model.add(
        Bidirectional(
            LSTM(
                shape["nr_hidden"],
                recurrent_dropout=settings["dropout"],
                dropout=settings["dropout"],
            )
        )
    )
    model.add(Dense(shape["nr_class"], activation="sigmoid"))
    model.compile(
        optimizer=Adam(lr=settings["lr"]),
        loss="binary_crossentropy",
        metrics=["accuracy"],
    )
    return model


def get_embeddings(vocab):
    return vocab.vectors.data


def evaluate(model_dir, texts, labels, max_length=100):
    nlp = spacy.load("en_vectors_web_lg")
    nlp.add_pipe(nlp.create_pipe("sentencizer"))
    nlp.add_pipe(SentimentAnalyser.load(model_dir, nlp, max_length=max_length))

    correct = 0
    i = 0
    for doc in nlp.pipe(texts, batch_size=1000):
        correct += bool(doc.sentiment >= 0.5) == bool(labels[i])
        i += 1
    return float(correct) / i


# def read_data(data_dir, limit=0):
#     examples = []
#     for subdir, label in (("pos", 1), ("neg", 0)):
#         for filename in (data_dir / subdir).iterdir():
#             with filename.open() as file_:
#                 text = file_.read()
#             examples.append((text, label))
#     random.shuffle(examples)
#     if limit >= 1:
#         examples = examples[:limit]
#     return zip(*examples)  # Unzips into two lists

def read_data(data_dir, limit=0):
    df=pd.read_csv(data_dir / 'Tweet_Sentiments.csv')
    tweets = df['Tweet']
    sentiments = df['Sentiment']
    example=zip(tweets,sentiments)
    example=list(example)
    if limit >= 1:
        example = example[:limit]
    return zip(*example)# Unzips into two lists


@plac.annotations(
    # train_dir=("Location of training file or directory"),
    # dev_dir=("Location of development file or directory"),
    model_dir=("Location of output model directory",),
    is_runtime=("Demonstrate run-time usage", "flag", "r", bool),
    nr_hidden=("Number of hidden units", "option", "H", int),
    max_length=("Maximum sentence length", "option", "L", int),
    dropout=("Dropout", "option", "d", float),
    learn_rate=("Learn rate", "option", "e", float),
    nb_epoch=("Number of training epochs", "option", "i", int),
    batch_size=("Size of minibatches for training LSTM", "option", "b", int),
    nr_examples=("Limit to N examples", "option", "n", int),
)
def main(
    model_dir='model_lstm',
    is_runtime=False,
    nr_hidden=64,
    max_length=100,  # Shape
    dropout=0.5,
    learn_rate=0.001,  # General NN config
    nb_epoch=1,
    batch_size=256,
    nr_examples=-1,
):  # Training params
    if model_dir is not None:
        model_dir = pathlib.Path(model_dir)
    # if train_dir is None or dev_dir is None:
    #     imdb_data = thinc.extra.datasets.imdb()
    # if is_runtime:
    #     if dev_dir is None:
    #         dev_texts, dev_labels = zip(*imdb_data[1])
    #     else:
    #         dev_texts, dev_labels = read_data(dev_dir)
    #     acc = evaluate(model_dir, dev_texts, dev_labels, max_length=max_length)
    #     print(acc)
    # else:
    #     if train_dir is None:
    #         train_texts, train_labels = zip(*imdb_data[0])
    #     else:
    #         print("Read data")
    #         train_texts, train_labels = read_data(train_dir, limit=nr_examples)
    #     if dev_dir is None:
    #         dev_texts, dev_labels = zip(*imdb_data[1])
    #     else:
    #         dev_texts, dev_labels = read_data(dev_dir, limit=nr_examples)
        # print("Loading Train and Test Data.....")
        # with open('dev.txt','rb') as f:
        #     dev_docs=pickle.load(f)
        # with open('train.txt','rb') as f:
        #     train_docs=pickle.load(f)
        # print('Loading Complete..')
        # train_labels = numpy.asarray(train_labels, dtype="int32")
        # dev_labels = numpy.asarray(dev_labels, dtype="int32")
        lstm = train(
            {"nr_hidden": nr_hidden, "max_length": max_length, "nr_class": 1},
            {"dropout": dropout, "lr": learn_rate},
            {},
            nb_epoch=nb_epoch,
            batch_size=batch_size,
        )
        weights = lstm.get_weights()
        if model_dir is not None:
            with (model_dir / "model").open("wb") as file_:
                pickle.dump(weights[1:], file_)
            with (model_dir / "config.json").open("w") as file_:
                file_.write(lstm.to_json())


if __name__ == "__main__":
    plac.call(main)
