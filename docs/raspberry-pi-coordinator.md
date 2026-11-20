cd ~/StackChan/coordinator
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp config.example.yaml config.yaml   # 可選
# 對外給 StackChan 連：綁 0.0.0.0
uvicorn app.main:app --host 0.0.0.0 --port 8765