#!/bin/bash
#
# HLS Knowledge Base - 完整重新初始化腳本
# 此腳本會重置資料庫並重新導入所有數據
#

set -e  # 遇到錯誤立即停止

echo "============================================================"
echo "HLS Knowledge Base - 完整重新初始化"
echo "============================================================"
echo ""

# 切換到腳本所在目錄
cd "$(dirname "$0")"

echo "當前目錄: $(pwd)"
echo ""

# 1. 停止並移除容器和 volume
echo "[1/10] 停止並移除容器和 volume..."
docker-compose down -v
if [ $? -eq 0 ]; then
    echo "✓ 容器和 volume 已移除"
else
    echo "✗ 移除失敗"
    exit 1
fi
echo ""

# 2. 確認 volume 已刪除
echo "[2/10] 確認 volume 已刪除..."
VOLUMES=$(docker volume ls | grep -c "hls-knowledge-base" || true)
if [ "$VOLUMES" -eq 0 ]; then
    echo "✓ Volume 已完全清除"
else
    echo "⚠ 仍有 $VOLUMES 個相關 volume 存在"
fi
echo ""

# 3. 重新啟動容器
echo "[3/10] 重新啟動容器..."
docker-compose up -d
if [ $? -eq 0 ]; then
    echo "✓ 容器已啟動"
else
    echo "✗ 啟動失敗"
    exit 1
fi
echo ""

# 4. 等待 PostgreSQL 初始化
echo "[4/10] 等待 PostgreSQL 初始化（10秒）..."
sleep 10
echo "✓ 等待完成"
echo ""

# 5. 檢查 PostgreSQL 狀態
echo "[5/10] 檢查 PostgreSQL 狀態..."
for i in {1..10}; do
    if docker exec hls_knowledge_db pg_isready -U hls_user -d hls_knowledge > /dev/null 2>&1; then
        echo "✓ PostgreSQL 已就緒"
        break
    fi
    if [ $i -eq 10 ]; then
        echo "✗ PostgreSQL 未就緒，請檢查日誌：docker logs hls_knowledge_db"
        exit 1
    fi
    echo "  等待中... ($i/10)"
    sleep 2
done
echo ""

# 6. 檢查 schema
echo "[6/10] 驗證資料庫 schema..."
RULE_CODE=$(docker exec hls_knowledge_db psql -U hls_user -d hls_knowledge -t -c \
    "SELECT column_name FROM information_schema.columns WHERE table_name='hls_rules' AND column_name='rule_code';" | xargs)
RULE_TYPE=$(docker exec hls_knowledge_db psql -U hls_user -d hls_knowledge -t -c \
    "SELECT column_name FROM information_schema.columns WHERE table_name='hls_rules' AND column_name='rule_type';" | xargs)

if [ "$RULE_CODE" == "rule_code" ] && [ "$RULE_TYPE" == "rule_type" ]; then
    echo "✓ Schema 正確（包含 rule_code 和 rule_type）"
else
    echo "✗ Schema 不正確！"
    echo "  rule_code: $RULE_CODE"
    echo "  rule_type: $RULE_TYPE"
    exit 1
fi
echo ""

# 7. 重啟 API 容器
echo "[7/10] 重啟 API 容器..."
docker restart hls_kb_api
sleep 5
echo "✓ API 已重啟"
echo ""

# 8. 檢查 API 健康狀態
echo "[8/10] 檢查 API 健康狀態..."
for i in {1..10}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        HEALTH_STATUS=$(curl -s http://localhost:8000/health | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
        if [ "$HEALTH_STATUS" == "healthy" ]; then
            echo "✓ API 健康狀態：$HEALTH_STATUS"
            break
        fi
    fi
    if [ $i -eq 10 ]; then
        echo "✗ API 未就緒，請檢查日誌：docker logs hls_kb_api"
        exit 1
    fi
    echo "  等待中... ($i/10)"
    sleep 2
done
echo ""

# 9. 導入官方規則
echo "[9/10] 導入官方規則..."
if python3 import_hls_rules.py > /tmp/import_hls.log 2>&1; then
    OFFICIAL_COUNT=$(grep "成功插入.*條" /tmp/import_hls.log | grep -o '[0-9]*' | head -1)
    echo "✓ 成功導入 $OFFICIAL_COUNT 條官方規則"
else
    echo "✗ 導入失敗，請查看日誌：/tmp/import_hls.log"
    exit 1
fi
echo ""

# 10. 導入用戶提示
echo "[10/10] 導入用戶提示..."
if python3 import_user_prompts.py > /tmp/import_prompts.log 2>&1; then
    PROMPT_COUNT=$(grep "成功插入.*條" /tmp/import_prompts.log | grep -o '[0-9]*' | head -1)
    echo "✓ 成功導入 $PROMPT_COUNT 條用戶提示"
else
    echo "✗ 導入失敗，請查看日誌：/tmp/import_prompts.log"
    exit 1
fi
echo ""

# 最終驗證
echo "============================================================"
echo "最終驗證"
echo "============================================================"
echo ""

# 檢查總數
TOTAL=$(docker exec hls_knowledge_db psql -U hls_user -d hls_knowledge -t -c \
    "SELECT COUNT(*) FROM hls_rules;" | xargs)
OFFICIAL=$(docker exec hls_knowledge_db psql -U hls_user -d hls_knowledge -t -c \
    "SELECT COUNT(*) FROM hls_rules WHERE rule_type='official';" | xargs)
USER_PROMPT=$(docker exec hls_knowledge_db psql -U hls_user -d hls_knowledge -t -c \
    "SELECT COUNT(*) FROM hls_rules WHERE rule_type='user_prompt';" | xargs)

echo "資料庫統計："
echo "  官方規則 (official):    $OFFICIAL"
echo "  用戶提示 (user_prompt): $USER_PROMPT"
echo "  ─────────────────────────────"
echo "  總計:                   $TOTAL"
echo ""

# API 測試
echo "API 測試："
API_RULES=$(curl -s 'http://localhost:8000/api/rules/effective?min_success_rate=0&limit=1' | \
    grep -o '"rules":\[' > /dev/null && echo "✓" || echo "✗")
echo "  規則查詢: ${API_RULES}"
echo ""

if [ "$TOTAL" -ge 300 ] && [ "$OFFICIAL" -ge 280 ] && [ "$USER_PROMPT" -ge 10 ]; then
    echo "============================================================"
    echo "✓ 重新初始化完成！系統運作正常"
    echo "============================================================"
    echo ""
    echo "下一步："
    echo "  1. 訪問 API: curl http://localhost:8000/health"
    echo "  2. 查看規則: curl 'http://localhost:8000/api/rules/effective?min_success_rate=0&limit=5'"
    echo "  3. (可選) 導入範例項目: python3 import_fir128_data.py"
    echo ""
else
    echo "============================================================"
    echo "⚠ 重新初始化完成，但數據量異常"
    echo "============================================================"
    echo ""
    echo "預期："
    echo "  官方規則: ~287"
    echo "  用戶提示: ~15"
    echo "  總計: ~302"
    echo ""
    echo "實際："
    echo "  官方規則: $OFFICIAL"
    echo "  用戶提示: $USER_PROMPT"
    echo "  總計: $TOTAL"
    echo ""
fi
