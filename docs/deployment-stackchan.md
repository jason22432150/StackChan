# 如果在 python 虛擬環境中 要先退出虛擬環境
deactivate

source /Users/guo/esp/esp-idf-v6.1/export.sh
cd firmware/main/apps/app_companion
cp .env.example .env
# 編輯 COMPANION_PI_WS_URL / COMPANION_PI_TOKEN

cd ../../..   # → firmware/

# 改 .env 後務必 reconfigure
idf.py reconfigure build

# 自動燒錄 StackChan
idf.py flash

