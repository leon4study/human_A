# 파이썬 코드 예시
import pyvista as pv
import os


os.chdir("/Users/jun/GitStudy/human_A/sim")

# 1. 오픈폼 데이터 불러오기
reader = pv.OpenFOAMReader("result.foam")

# 2. 마지막 시간대(크랭크 각도) 데이터 선택
reader.set_active_time_value(reader.time_values[-1])
mesh = reader.read()

# 3. 내부 데이터 블록 가져오기 (보통 internalMesh)
internal_mesh = mesh["internalMesh"]

# 4. 온도(T), 압력(p) 데이터 추출! (이제 넘파이 배열로 맘대로 분석 가능)
temperature = internal_mesh.cell_data["T"]
pressure = internal_mesh.cell_data["p"]

print(f"최고 온도: {temperature.max()} K")
print(f"평균 압력: {pressure.mean()}")

# 5. 파이썬에서 바로 3D 시각화 띄우기
internal_mesh.plot(scalars="T", cmap="inferno")
