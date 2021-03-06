#!//usr/bin/python
#Davy Ragland | dragland@stanford.edu
#Adrien Truong | aqtruong@stanford.edu
#CS231N_REDDIT_NET | 2018

#*********************************** SETUP *************************************
import sys
import os
import argparse
import json
import pickle
import numpy as np
import matplotlib.pyplot as plt
from itertools import product
import PIL
from PIL import Image, ImageOps
from keras.applications import VGG16
from keras import models
from keras import layers
from keras import optimizers
from keras.utils.vis_utils import plot_model
from keras.callbacks import ModelCheckpoint, EarlyStopping
from sklearn.metrics import confusion_matrix
from vis.visualization import visualize_saliency
plt.switch_backend('agg')

NUM_CLASSES=20
train_path_default = "train.json"
train_small_path_default = "small_train.json"
validation_path = "validation.json"

experiments_path ="experiments/"
test_path = "000"
config_path = "/config.json"
model_output = "/model_graph.png"
model_history = "/test.h5"
best_weights = "/best.h5"
score_output = "/val_acc.txt"
acc_output = "/acc.png"
loss_output = "/loss.png"
confused_output = "/confused.png"
saliency_output = "/saliency.png"

learning_rate_default = 1e-4
epochs_default = 15

#*********************************** HELPERS ***********************************
def get_data(json_path):
    X_train = []
    y_train = []
    with open(json_path) as f:
        data = json.load(f)
        for post in data['posts']:
            path = post['path']
            label = post['subreddit']
            img = np.array(Image.open(path))
            X_train.append(img)

            one_hot = np.zeros(NUM_CLASSES)
            one_hot[label] = 1
            y_train.append(one_hot)

    X_train = np.array(X_train)
    y_train = np.array(y_train)

    return X_train, y_train

def get_subreddit_indices_map(path):
    with open(path) as f:
        data = json.load(f)
        return data['subreddit_indices_map']

def get_subreddit_for_index(index):
    subreddit_indices_map = get_subreddit_indices_map(train_path_default)
    reverse_map = {}
    for k, v in subreddit_indices_map.items():
        reverse_map[v] = k
    return reverse_map[index]

def create_model(size):
    vgg_conv = VGG16(weights='imagenet', include_top=False, input_shape=(size, size, 3))
    for layer in vgg_conv.layers[:-4]:
        layer.trainable = False
    model = models.Sequential()
    model.add(vgg_conv)
    model.add(layers.GlobalAveragePooling2D())
    model.add(layers.Dense(1024, activation='relu'))
    model.add(layers.Dropout(0.25))
    model.add(layers.Dense(NUM_CLASSES, activation='softmax'))
    model.summary()
    #plot_model(model, to_file=config.path + model_output, show_shapes=True, show_layer_names=True)
    return model

def plot_history(history, config):
    plt.gcf().clear()
    plt.plot(history['acc'], 'ro', markersize=12)
    plt.plot(history['val_acc'], 'go', markersize=12)
    plt.title('Training and validation accuracy' + str(config.l))
    plt.ylabel('accuracy')
    plt.xlabel('epoch')
    plt.legend(['train', 'validation'], loc='upper left')
    plt.savefig(config.path + acc_output)
    # plt.show()
    plt.gcf().clear()
    plt.plot(history['loss'], 'ro', markersize=12)
    plt.plot(history['val_loss'], 'go', markersize=12)
    plt.title('Training and validation loss of lr=' + str(config.l))
    plt.ylabel('loss')
    plt.xlabel('epoch')
    plt.legend(['train', 'validation'], loc='upper left')
    plt.savefig(config.path + loss_output)
    # plt.show()

def score(config):
    X_train, y_train = get_data(config.train_path)
    X_val, y_val = get_data(validation_path)
    model = create_model(X_train.shape[1])
    model.load_weights(config.path + best_weights)
    model.compile(loss='categorical_crossentropy', optimizer=optimizers.Adam(lr=config.l), metrics=['accuracy'])
    scores = model.evaluate(X_val, y_val, verbose=1)
    print("validation accuracy of " + str(100 * scores[1]) + "%...")
    with open(config.path + score_output, 'a') as f:
        f.write(str(100 * scores[1]) + "%\n")
    
def plot_confusion_matrix(config):
    X_train, y_train = get_data(config.train_path)
    y_train = np.argmax(y_train, axis=1)
    model = create_model(X_train.shape[1])
    model.load_weights(config.path + best_weights)
    model.compile(loss='categorical_crossentropy', optimizer=optimizers.Adam(lr=config.l), metrics=['accuracy'])
    indices_map = get_subreddit_indices_map(train_path_default)
    classes = sorted(indices_map.keys(), key=lambda k: indices_map[k])
    preds = np.argmax(model.predict(X_train), axis=1)
    cm = confusion_matrix(y_train, preds)
    plt.gcf().clear()
    plt.figure()
    plt.imshow(cm, interpolation='nearest', cmap=plt.cm.Blues)
    plt.title('Confusion Matrix')
    plt.colorbar()
    tick_marks = np.arange(len(classes))
    plt.xticks(tick_marks, classes, rotation=90)
    plt.yticks(tick_marks, classes)
    thresh = cm.max() / 2.
    for i, j in product(range(cm.shape[0]), range(cm.shape[1])):
        plt.text(j, i, format(cm[i, j], 'd'),
                 horizontalalignment="center",
                 color="white" if cm[i, j] > thresh else "black")
    plt.tight_layout()
    plt.ylabel('True label')
    plt.xlabel('Predicted label')
    plt.savefig(config.path + confused_output)
    # plt.show()

def plot_saliency(config):
    X_train, y_train = get_data(config.train_path)
    model = create_model(X_train.shape[1])
    model.load_weights(config.path + best_weights)
    img = Image.open(config.i).convert('RGB')
    new = ImageOps.fit(img, (X_train.shape[1], X_train.shape[2]), Image.ANTIALIAS)
    # new.show()
    img = np.array(new)
    model.compile(loss='categorical_crossentropy', optimizer=optimizers.Adam(lr=config.l), metrics=['accuracy'])
    out = visualize_saliency(model, len(model.layers) - 2, None, img, backprop_modifier=None, grad_modifier="absolute")
    out = PIL.Image.fromarray(out)
    # out.show()
    out.save(config.path + saliency_output)

def train(config):
    print("training model...")
    X_train, y_train = get_data(config.train_path)
    X_val, y_val = get_data(validation_path)
    model = create_model(X_train.shape[1])
    model.compile(loss='categorical_crossentropy', optimizer=optimizers.Adam(lr=config.l), metrics=['accuracy'])
    checkpoint = ModelCheckpoint(config.path + best_weights, monitor='val_acc', verbose=1, save_best_only=True, mode='max')
    early_stopping = EarlyStopping(monitor='val_loss', patience=2)
    history = model.fit(X_train, y_train, validation_data=(X_val, y_val), batch_size=32, epochs=config.n, callbacks=[checkpoint], verbose=1)
    with open(config.path + model_history, 'wb') as f:
        pickle.dump(history.history, f)
    
def evaluate(config):
    print("evaluating model...")
    with open(config.path + model_history, 'rb') as f:
        plot_history(pickle.load(f), config)
    score(config)
    plot_confusion_matrix(config)

def predict(config):
    print("predicting class for image...")
    X_train, y_train = get_data(config.train_path)
    model = create_model(X_train.shape[1])
    model.load_weights(config.path + best_weights)
    img = Image.open(config.i).convert('RGB')
    new = ImageOps.fit(img, (X_train.shape[1], X_train.shape[2]), Image.ANTIALIAS)
    img = np.array(new)
    pred = model.predict(np.array([img]))[0]
    print(pred)
    label_i = np.argmax(pred)
    label = get_subreddit_for_index(label_i)
    print("predictiing[" + str(label_i) + "]: " + label)
    plot_saliency(config)

#************************************ MAIN *************************************
if __name__ == "__main__":
    print(sys.version)
    print("Executing program:")
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", type=str, help='path to save experiment')
    parser.add_argument("-s", action="store_true", help="use small training set")
    parser.add_argument("-t", action="store_true", help="train classifier")
    parser.add_argument('-l', type=float, help='learning rate')
    parser.add_argument("-n", type=int, help="number of epochs to run")
    parser.add_argument("-e", action="store_true", help="evaluate classifier")
    parser.add_argument("-i", type=str, help='path of img to predict')
    config = parser.parse_args()

    if len(sys.argv) <= 1:
        print('Invalid mode! Aborting...')
        print("example usage: ")
        print("python classifier.py -t -l=5e-5 -n=20 -e -i=datasets/cats50.jpg")

    else:
        if config.p:
            config.path = experiments_path + config.p
            if not os.path.isdir(config.path):
                os.mkdir(config.path);
        else:
            if os.listdir(experiments_path):
                count = sorted(os.listdir(experiments_path))[-1]
                config.path = experiments_path + str(int('9' + count) + 1)[1:]
            else:
                config.path = experiments_path + test_path
            os.mkdir(config.path);

        config.train_path = train_path_default
        if config.s:
            config.train_path = train_small_path_default
        if config.l == None:
            config.l = learning_rate_default
        if config.n == None:
            config.n = epochs_default
        print(config)
        with open(config.path + config_path, "w") as f:  
            json.dump(vars(config), f)
        if config.t:
            train(config)
        if config.e:
            evaluate(config)
        if config.i:
            predict(config)