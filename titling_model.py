import numpy as np
from keras.models import Model, load_model
from keras import backend as K

from keras.applications.vgg16 import VGG16
from keras.layers import Dense, GlobalAveragePooling2D, Input, LSTM, Embedding, TimeDistributed, Reshape, Activation, Concatenate
# some code borrowed from https://blog.keras.io/using-pre-trained-word-embeddings-in-a-keras-model.html

PROJECTION_LAYER = 'projection'
LSTM_LAYER = 'lstm'
SOFTMAX_LAYER = 'softmax'
EMBEDDING_LAYER = 'embedding'

START_TOKEN = '<START>'
PAD_TOKEN = '<PAD>'
UNKNOWN_TOKEN = '<UNK>'
END_TOKEN = '<END>'

class ImageTitlingModel(object):
    def __init__(self, embedding_matrix, words_by_id, id_by_words, num_subreddits=20, max_len=20):
        self.num_subreddits = num_subreddits
        self.max_len = max_len
        self.embedding_matrix = embedding_matrix
        self.words_by_id = words_by_id
        self.id_by_words = id_by_words

        self.lstm_size = 256

        self.create_models(self.lstm_size, embedding_matrix, num_subreddits, max_len)

    def load_checkpoint(self, save_file):
        self.train_model = load_model(save_file)
        set_inference_weights_from_train()

    def load_weights(self, save_file):
        self.train_model.load_weights(save_file)
        set_inference_weights_from_train()

    def generate_title(self, img, subreddit):
        subreddit_one_hot = np.zeros(self.num_subreddits)
        subreddit_one_hot[subreddit] = 1
        encoder_output = self.inference_encoder_model.predict([np.array([img]), np.array([subreddit_one_hot])])

        zero_h = np.zeros((encoder_output.shape[0], self.lstm_size))
        zero_c = np.zeros((encoder_output.shape[0], self.lstm_size))
        _, initial_h, initial_c = self.inference_decoder_model.predict([encoder_output, zero_h, zero_c])

        start_id = self.id_by_words[START_TOKEN]
        start_embedding = self.embedding_matrix[start_id]
        prev_h = initial_h
        prev_c = initial_c
        prev_word = start_embedding
        title = []
        end_id = self.id_by_words[END_TOKEN]
        while len(title) < self.max_len:
            probs, h, c = self.inference_decoder_model.predict([np.array([prev_word]), prev_h, prev_c])
            predicted_word_id = np.argmax(probs)

            if predicted_word_id == end_id:
                break

            predicted_word = self.words_by_id[predicted_word_id]
            title.append(predicted_word)

            prev_word = self.embedding_matrix[predicted_word_id]
            prev_h = h
            prev_c = c

        return ' '.join(title)

    def set_inference_weights_from_train(self):
        inference_models = [self.inference_encoder_model, self.inference_decoder_model]
        inference_layers = []
        for model in inference_models:
            inference_layers += model.layers
        train_layers_by_name = {layer.name: layer for layer in self.train_model.layers}
        for inference_layer in inference_layers:
            train_layer = train_layers_by_name[layer.name]
            inference_layer.weights = train_layer.weights

    def create_models(self, lstm_size, embedding_matrix, num_subreddits, max_len):
        cnn_encoder = VGG16(weights='imagenet', include_top=False)
        for layer in cnn_encoder.layers:
            layer.trainable = False

        vocab_size = embedding_matrix.shape[0]
        word_embeddings_size = embedding_matrix.shape[1]

        one_hot_subreddit = Input(shape=(num_subreddits,), dtype='float32', name='subreddit_input')
        features = cnn_encoder.output
        features = GlobalAveragePooling2D()(features)
        features_concat = Concatenate()([features, one_hot_subreddit])

        encoder_output = Dense(word_embeddings_size, name=PROJECTION_LAYER)(features_concat)

        # decoding changes between training and testing
        # during training, we feed the ground truth prev word into the LSTM
        # during inference, we feed the output of the LSTM back into the LSTM

        # training model
        train_titles = Input(shape=(max_len,), dtype='int32', name='train_titles_input')
        train_embedding_layer = Embedding(vocab_size,
            word_embeddings_size,
            weights=[embedding_matrix],
            input_length=max_len,
            mask_zero=True,
            trainable=False,
            name=EMBEDDING_LAYER)
        train_embeddings = train_embedding_layer(train_titles)

        encoder_output_reshaped = Reshape((1, -1))(encoder_output)
        train_decoder = LSTM(lstm_size, return_sequences=True, return_state=True, name=LSTM_LAYER)
        _, train_initial_h, train_initial_c = train_decoder(encoder_output_reshaped)
        train_hidden_states, _, _ = train_decoder(train_embeddings, [train_initial_h, train_initial_c])
        train_scores = TimeDistributed(Dense(vocab_size, name=SOFTMAX_LAYER))(train_hidden_states)
        train_probs = Activation('softmax')(train_scores)

        self.train_model = Model(inputs=[cnn_encoder.inputs[0], one_hot_subreddit, train_titles], outputs=[train_probs])

        # inference encoder
        self.inference_encoder_model = Model(inputs=[cnn_encoder.inputs[0], one_hot_subreddit], outputs=encoder_output)

        # inference decoder for words
        prev_word = Input(shape=(word_embeddings_size,), dtype='float32', name='prev_word')
        prev_h = Input(shape=(lstm_size,), dtype='float32', name='prev_h')
        prev_c = Input(shape=(lstm_size,), dtype='float32', name='prev_c')

        inference_decoder = LSTM(lstm_size, return_sequences=True, return_state=True, name=LSTM_LAYER)
        prev_word_reshaped = Reshape((1, -1))(prev_word)
        inference_h, state_h, state_c = inference_decoder(prev_word_reshaped, initial_state=[prev_h, prev_c])
        inference_scores = Dense(vocab_size, name=SOFTMAX_LAYER)(inference_h)
        inference_probs = Activation('softmax')(inference_scores)

        self.inference_decoder_model = Model(inputs=[prev_word, prev_h, prev_c], outputs=[inference_probs, state_h, state_c])
