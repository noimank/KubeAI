#!/bin/sh
set -e

# 根据环境变量生成运行时配置文件，默认值兜底
cat > /usr/share/nginx/html/config.js << EOF
window.__RUNTIME_CONFIG__ = {
  APP_TITLE: '${APP_TITLE:-KubeAI}',
};
EOF

exec "$@"
