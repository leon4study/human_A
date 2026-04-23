# src/model_builder.py
from tensorflow.keras.models import Model
from tensorflow.keras.layers import Input, Dense, Dropout


def build_autoencoder(input_dim: int) -> Model:
    """
    시간 피처와 센서 피처 간의 복잡한 비선형 관계를 학습할 수 있도록
    충분한 용량(Capacity)을 가진 Deep AutoEncoder 모델을 생성합니다.
    """
    # 병목층 크기는 최소 4개 이상 보장하여 정보 손실 방지
    bottleneck_size = max(4, input_dim // 4)

    input_layer = Input(shape=(input_dim,))

    # 🌟 인코더 (Encoder): 8로 바로 짓누르지 않고, 32 -> 16으로 서서히 압축합니다.
    encoded = Dense(32, activation="relu")(input_layer)
    encoded = Dropout(0.1)(encoded)  # 과적합 방지
    encoded = Dense(16, activation="relu")(encoded)

    # 병목 (Bottleneck)
    encoded = Dense(bottleneck_size, activation="relu")(encoded)

    # 🌟 디코더 (Decoder): 다시 16 -> 32로 대칭을 맞춰 넓혀줍니다.
    decoded = Dense(16, activation="relu")(encoded)
    decoded = Dense(32, activation="relu")(decoded)

    # 출력층
    output_layer = Dense(input_dim, activation="sigmoid")(decoded)

    autoencoder = Model(inputs=input_layer, outputs=output_layer)
    autoencoder.compile(optimizer="adam", loss="mse")

    return autoencoder
