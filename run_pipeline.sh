#!/bin/bash
echo "🚀 스마트팜 예지보전 파이프라인 가동을 시작합니다..."

echo "1. 패키지 설치 중..."
pip install -r requirements.txt

echo "2. 오토인코더 모델 학습 시작..."
python src/train.py

echo "3. 테스트 데이터로 추론 및 RCA 로그 생성..."
python src/inference.py

echo "✅ 모든 파이프라인이 성공적으로 완료되었습니다!"