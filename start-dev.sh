#!/bin/bash
# ============================================================
# start-dev.sh  —  Local development startup script
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║        HedgeSwarm Full-Stack Dev Environment               ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 is required${NC}"
    exit 1
fi

# Check Node
if ! command -v node &> /dev/null; then
    echo -e "${RED}Error: Node.js is required${NC}"
    exit 1
fi

# Setup Python venv if not exists
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}Creating Python virtual environment...${NC}"
    python3 -m venv .venv
fi

echo -e "${YELLOW}Installing Python dependencies...${NC}"
source .venv/bin/activate
pip install -q -r requirements.txt

# Setup frontend
echo -e "${YELLOW}Installing frontend dependencies...${NC}"
cd frontend
if [ ! -d "node_modules" ]; then
    npm install
fi
cd ..

echo -e "${GREEN}✓ Dependencies installed${NC}"
echo ""
echo -e "${BLUE}Starting services...${NC}"
echo -e "  ${YELLOW}→${NC} API Server:     ${GREEN}http://localhost:3003${NC}"
echo -e "  ${YELLOW}→${NC} Frontend Dev:   ${GREEN}http://localhost:3000${NC}"
echo -e "  ${YELLOW}→${NC} Streamlit:      ${GREEN}http://localhost:8501${NC} (legacy)"
echo ""

# Start unified full-stack server (engine + API in one process)
echo -e "${YELLOW}Starting unified engine + API server...${NC}"
source .venv/bin/activate
python main_fullstack.py &
API_PID=$!

# Start frontend dev server in background
echo -e "${YELLOW}Starting frontend dev server...${NC}"
cd frontend
npm run dev &
FE_PID=$!
cd ..

echo ""
echo -e "${GREEN}All services started! Press Ctrl+C to stop.${NC}"
echo ""

# Trap SIGINT to kill both processes
cleanup() {
    echo -e "${YELLOW}Shutting down...${NC}"
    kill $API_PID 2>/dev/null || true
    kill $FE_PID 2>/dev/null || true
    echo -e "${GREEN}✓ Stopped${NC}"
    exit 0
}
trap cleanup SIGINT SIGTERM

# Wait for both
wait $API_PID $FE_PID
