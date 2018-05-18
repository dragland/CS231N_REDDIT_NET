import argparse
import os

import json

import numpy as np
from PIL import Image

from keras.applications.vgg16 import VGG16
from keras.preprocessing import image
from keras.models import Model, load_model, Sequential
from keras.layers import Dense, GlobalAveragePooling2D
from keras import backend as K
from keras.preprocessing.image import ImageDataGenerator
from keras.optimizers import Adam
from keras import metrics
from keras.callbacks import TensorBoard, ModelCheckpoint, Callback

NUM_CLASSES=20

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

def create_model():
    # create the base pre-trained model
    base_model = VGG16(weights='imagenet', include_top=False)

    x = base_model.output
    x = GlobalAveragePooling2D()(x)
    x = Dense(1024, activation='relu')(x)
    predictions = Dense(NUM_CLASSES, activation='softmax')(x)

    # this is the model we will train
    model = Model(inputs=base_model.input, outputs=predictions)

    # first: train only the top layers (which were randomly initialized)
    # i.e. freeze all convolutional InceptionV3 layers
    for layer in base_model.layers:
        layer.trainable = False

    return model

class EpochSaver(Callback):
    def __init__(self, path):
        self.path = path

    def on_epoch_end(self, epoch, logs=None):
        with open(self.path, 'w') as f:
            json.dump({'epoch': epoch}, f)

def train(config):
    latest_checkpoint_path = config.experiment_dir + 'latest-checkpoint.h5'
    epoch_path = config.experiment_dir + 'last_epoch.json'
    initial_epoch = 0
    if os.path.exists(latest_checkpoint_path):
        model = load_model(latest_checkpoint_path)
        with open(epoch_path) as f:
            initial_epoch = json.load(f)['epoch'] + 1
            print('Loading model from last checkpoint and resuming training on epoch {}'.format(initial_epoch))
    else:
        print('Starting new training run')
        model = create_model()

    # record what params we trained with
    with open(config.experiment_dir + 'config.json', 'w') as f:
        json.dump(vars(config), f)

    model.compile(optimizer=Adam(lr=config.lr), loss='categorical_crossentropy', metrics=['accuracy'])

    X_train, y_train = get_data('train.json')
    X_val, y_val = get_data('validation.json')
    # train the model on the new data for a few epochs
    best_checkpoint_file_path = config.experiment_dir + 'best-checkpoint.hdf5'
    best_checkpoint = ModelCheckpoint(best_checkpoint_file_path, monitor='val_acc', verbose=1, save_best_only=True, mode='max', save_weights_only=True)
    latest_checkpoint = ModelCheckpoint(latest_checkpoint_path, verbose=1, save_best_only=False, mode='max')
    epoch_saver = EpochSaver(epoch_path)
    tensorboard = TensorBoard(log_dir=config.experiment_dir, histogram_freq=0, write_graph=False, write_images=True)
    model.fit(X_train, y_train,
        validation_data=(X_val, y_val),
        batch_size=config.batch_size,
        epochs=config.epochs,
        initial_epoch=initial_epoch,
        callbacks=[best_checkpoint, latest_checkpoint, epoch_saver, tensorboard])

def evaluate(config):
    model = create_model()
    checkpoint_file_path = config.experiment_dir + 'best-checkpoint.hdf5'
    model.load_weights(checkpoint_file_path)

    X_train, y_train = get_train_data()
    preds = model.predict(X_train)

    with open('model.json') as f:
        data = json.load(f)
        subreddit_indices_map = data['subreddit_indices_map']
        reverse_map = {}
        for k, v in subreddit_indices_map.items():
            reverse_map[v] = k
        num_correct = 0
        for i, post in enumerate(data['posts']):
            probs = preds[i]
            prediction_i = np.argmax(probs)
            subreddit = reverse_map[prediction_i]
            if prediction_i == post['subreddit']:
                num_correct += 1
            print(post)
            print(probs)
            print(subreddit)
            print('-' * 50)
        print('num correct: ', num_correct, ' total: ', len(data['posts']))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--experiment', type=str, help='unique experiment name')
    parser.add_argument('--lr', type=float, help='learning rate')
    parser.add_argument('--mode', type=str, help='train, evaluate')
    parser.add_argument('--batch_size', type=int, help='batch size')
    parser.add_argument('--epochs', type=int, help='number of epochs to train for')
    config = parser.parse_args()

    experiment_dir = 'experiments/{}/'.format(config.experiment)
    config.experiment_dir = experiment_dir
    if not os.path.isdir(experiment_dir):
        os.makedirs(experiment_dir)

    if config.mode == 'train':
        print('Training...')
        train(config)
    elif config.mode == 'evaluate':
        print('Evaluating...')
        evaluate(config)
    else:
        print('Invalid mode! Aborting...')
