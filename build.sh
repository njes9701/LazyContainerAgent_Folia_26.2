#!/usr/bin/env bash
# 建置 LazyContainerAgent:
#  1) mvn package      → agent 類別(Runtime/AgentMain/Transformer)+ shaded/relocated ASM + agent manifest
#  2) javac template   → 對「真實 1.21.11 mojmap NMS」編譯 LazyContainerTemplate(產生正確的 NMS 符號 bytecode)
#  3) jar uf           → 把 template .class 當 passive resource 注入 shaded jar(執行期只被讀 bytes、不被載入為類別)
set -euo pipefail
cd "$(dirname "$0")"

JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/jdk-21-oracle-x64}"
export JAVA_HOME
export PATH="$JAVA_HOME/bin:$PATH"

if [ ! -d nms-lib ] || [ -z "$(ls -A nms-lib/*.jar 2>/dev/null)" ]; then
  echo "ERROR: nms-lib/ 缺少 NMS 編譯相依 jar(你的 Paper 伺服器核心的 NMS libraries)。" >&2
  exit 1
fi
NMSCP="$(ls nms-lib/*.jar | tr '\n' ':')"

echo "== 1. mvn package =="
mvn -q -B clean package

JAR="target/LazyContainerAgent.jar"
[ -f "$JAR" ] || { echo "ERROR: $JAR 未產生" >&2; exit 1; }

echo "== 2. compile template against real NMS (+ agent classes for LazyContainerRuntime) =="
rm -rf template-out && mkdir -p template-out
javac -proc:none -nowarn -cp "${NMSCP}:target/classes" -d template-out \
  template/io/github/kuohsuanlo/lazycontainer/LazyContainerTemplate.java

echo "== 3. inject template .class into shaded jar =="
( cd template-out && jar uf "../$JAR" io/github/kuohsuanlo/lazycontainer/LazyContainerTemplate.class )

echo "== 4. verify =="
echo "-- manifest --"
unzip -p "$JAR" META-INF/MANIFEST.MF | grep -E 'Premain|Agent-Class|Retransform|Redefine' || true
echo "-- key entries --"
unzip -l "$JAR" | grep -E 'lazycontainer/(LazyContainer(Agent|Runtime|Transformer|Template)|asm/)' | head -20
echo "-- relocated ASM present? --"
unzip -l "$JAR" | grep -c 'io/github/kuohsuanlo/lazycontainer/asm/' || true
echo "DONE: $(readlink -f "$JAR")"
