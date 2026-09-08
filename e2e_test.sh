#!/usr/bin/env bash
# End-to-end HTTP test including the multi-method payment flow.
set -u
B=http://127.0.0.1:8901
P=0; F=0
CJ=$(mktemp /tmp/raffle-e2e-cookie.XXXXXX)
CURL="curl -s -b $CJ -c $CJ"
ok(){ echo "  PASS  $1"; P=$((P+1)); }
no(){ echo "  FAIL  $1"; F=$((F+1)); }
chk(){ [ "$2" = "$3" ] && ok "$1 ($2)" || no "$1 (got $2 want $3)"; }
stat(){ $CURL $B/api/raffle/$1/stats | python3 -c "import sys,json;print(json.load(sys.stdin)['$2'])"; }

if [ -z "${ADMIN_PASSWORD:-}" ]; then
  echo "ERROR: ADMIN_PASSWORD must be set for e2e_test.sh"
  exit 2
fi

echo "=============================================="
echo "0. Admin authentication"
echo "=============================================="
C=$(curl -s -o /dev/null -w "%{http_code}" $B/admin/6)
chk "admin GET without cookie redirects" "$C" "303"
C=$(curl -s -o /dev/null -w "%{http_code}" -X POST $B/admin/create -d "name=blocked")
chk "admin POST without cookie rejected" "$C" "401"
C=$($CURL -o /dev/null -w "%{http_code}" -X POST $B/admin/login \
  --data-urlencode "password=$ADMIN_PASSWORD" --data-urlencode "next=/admin/6")
chk "admin login accepted" "$C" "303"

echo "=============================================="
echo "1. Create raffle"
echo "=============================================="
C=$($CURL -o /dev/null -w "%{http_code}" -X POST $B/admin/create \
  -d "name=E2E Payment Raffle" -d "ticket_price=20.00" \
  -d "prize_1=TV" -d "prize_2=Tablet" -d "prize_3=Cash" -d "prize_4=Dinner")
chk "create returns redirect" "$C" "303"
RID=$($CURL $B/ | grep -oP '(?<=/raffle/)\d+' | head -1)
echo "  raffle id = $RID"

echo
echo "=============================================="
echo "2. Payment methods advertised"
echo "=============================================="
M=$($CURL $B/api/methods)
for k in card apple_pay google_pay cashapp venmo zelle cash; do
  echo "$M" | grep -q "\"$k\"" && ok "$k offered" || no "$k missing"
done
MOCK=$(echo "$M" | python3 -c "import sys,json;print(json.load(sys.stdin)['mock_mode'])")
echo "  mock_mode = $MOCK"

echo
echo "=============================================="
echo "3. Buy page renders all methods"
echo "=============================================="
BP=$($CURL $B/raffle/$RID)
echo "$BP" | grep -q "Cash App Pay" && ok "Cash App on buy page" || no "Cash App missing"
echo "$BP" | grep -q "Apple Pay"     && ok "Apple Pay on buy page" || no "Apple Pay missing"
echo "$BP" | grep -q "Venmo"         && ok "Venmo on buy page" || no "Venmo missing"
echo "$BP" | grep -q "Zelle"         && ok "Zelle on buy page" || no "Zelle missing"

echo
echo "=============================================="
echo "4. CARD purchase -> gateway -> paid"
echo "=============================================="
L=$($CURL -o /dev/null -w "%{redirect_url}" -X POST $B/buy \
  -d "raffle_id=$RID" -d "name=Card Carl" -d "email=carl@e2e.com" -d "phone=7705550001" \
  -d "quantity=5" -d "payment_method=card")
echo "  redirected to: $L"
echo "$L" | grep -q "mock-pay" && ok "routed to gateway" || no "no gateway redirect"
CODE=$(echo "$L" | grep -oP '(?<=mock-pay/)[A-Z0-9]+')
chk "pool still 0 before payment" "$(stat $RID tickets_sold)" "0"
chk "5 pending before payment" "$(stat $RID tickets_pending)" "5"
C=$($CURL -o /dev/null -w "%{http_code}" -X POST $B/mock-pay/$CODE/complete)
chk "pay completes" "$C" "303"
chk "5 tickets now active" "$(stat $RID tickets_sold)" "5"
chk "revenue 100.00" "$(stat $RID revenue)" "100.0"

echo
echo "=============================================="
echo "5. ZELLE purchase -> pending, NOT in pool"
echo "=============================================="
L=$($CURL -o /dev/null -w "%{redirect_url}" -X POST $B/buy \
  -d "raffle_id=$RID" -d "name=Zelle Zoe" -d "email=zoe@e2e.com" -d "phone=7705550002" \
  -d "quantity=10" -d "payment_method=zelle")
echo "$L" | grep -q "/pay/" && ok "routed to offline instructions" || no "wrong route"
ZCODE=$(echo "$L" | grep -oP '(?<=/pay/)[A-Z0-9]+')
PAGE=$($CURL $B/pay/$ZCODE)
echo "$PAGE" | grep -q "RAF-" && ok "memo code shown" || no "no memo code"
echo "$PAGE" | grep -q "Zelle" && ok "Zelle instructions rendered" || no "no instructions"
chk "pool STILL 5 (unpaid excluded)" "$(stat $RID tickets_sold)" "5"
chk "10 pending" "$(stat $RID tickets_pending)" "10"
chk "revenue STILL 100 (unconfirmed excluded)" "$(stat $RID revenue)" "100.0"
chk "pending revenue 200" "$(stat $RID revenue_pending)" "200.0"

echo
echo "=============================================="
echo "6. Odds ignore pending tickets"
echo "=============================================="
O=$($CURL "$B/api/odds?raffle_id=$RID&tickets=5")
PB=$(echo "$O" | python3 -c "import sys,json;print(json.load(sys.stdin)['pool_would_be'])")
chk "odds pool = 5 active + 5 new = 10" "$PB" "10"
echo "  -> the 10 unpaid Zelle tickets correctly excluded"

echo
echo "=============================================="
echo "7. Drum list excludes pending"
echo "=============================================="
CSV=$($CURL $B/admin/$RID/drum.csv)
LINES=$(echo "$CSV" | wc -l)
chk "CSV = 6 lines (5 paid + header)" "$LINES" "6"
echo "$CSV" | grep -q "Zelle Zoe" && no "unpaid buyer LEAKED into drum" || ok "unpaid buyer excluded"

echo
echo "=============================================="
echo "8. Admin approval queue"
echo "=============================================="
A=$($CURL $B/admin/$RID)
echo "$A" | grep -q "Pending approvals" && ok "approval queue shown" || no "no queue"
echo "$A" | grep -q "Zelle Zoe" && ok "Zoe listed for approval" || no "Zoe missing"
echo "$A" | grep -q "Approve" && ok "approve button present" || no "no approve button"

echo
echo "=============================================="
echo "9. Admin approves -> tickets activate"
echo "=============================================="
C=$($CURL -o /dev/null -w "%{http_code}" -X POST $B/admin/confirm/$ZCODE)
chk "approve redirects" "$C" "303"
chk "pool now 15" "$(stat $RID tickets_sold)" "15"
chk "pending drained to 0" "$(stat $RID tickets_pending)" "0"
chk "revenue now 300" "$(stat $RID revenue)" "300.0"

echo
echo "=============================================="
echo "10. Receipt shows correct state"
echo "=============================================="
R=$($CURL $B/receipt/$CODE)
echo "$R" | grep -q "chance to win" && ok "paid receipt shows odds" || no "no odds"
echo "$R" | grep -q 'badge paid'    && ok "paid badge shown" || no "no paid badge"

L=$($CURL -o /dev/null -w "%{redirect_url}" -X POST $B/buy \
  -d "raffle_id=$RID" -d "name=Pending Pat" -d "email=pat@e2e.com" -d "phone=7705550003" -d "quantity=3" -d "payment_method=zelle")
PCODE=$(echo "$L" | grep -oP '(?<=/pay/)[A-Z0-9]+')
R2=$($CURL $B/receipt/$PCODE)
echo "$R2" | grep -q "PAYMENT PENDING" && ok "pending warning shown" || no "no pending warning"
echo "$R2" | grep -q "not in the drawing yet" && ok "explains exclusion" || no "no explanation"

echo
echo "=============================================="
echo "11. Admin rejects an order"
echo "=============================================="
C=$($CURL -o /dev/null -w "%{http_code}" -X POST $B/admin/reject/$PCODE)
chk "reject redirects" "$C" "303"
chk "pending back to 0" "$(stat $RID tickets_pending)" "0"
chk "pool unchanged at 15" "$(stat $RID tickets_sold)" "15"

echo
echo "=============================================="
echo "12. Webhook signature enforcement"
echo "=============================================="
C=$($CURL -o /dev/null -w "%{http_code}" -X POST $B/webhook/stripe \
  -H "Content-Type: application/json" -d '{"type":"checkout.session.completed"}')
chk "unsigned webhook rejected" "$C" "400"
C=$($CURL -o /dev/null -w "%{http_code}" -X POST $B/webhook/stripe \
  -H "Stripe-Signature: t=1,v1=forged" -d '{"type":"x"}')
chk "forged signature rejected" "$C" "400"

echo
echo "=============================================="
echo "13. Cancel flow releases tickets"
echo "=============================================="
L=$($CURL -o /dev/null -w "%{redirect_url}" -X POST $B/buy \
  -d "raffle_id=$RID" -d "name=Bail Bob" -d "email=bob@e2e.com" -d "phone=7705550004" -d "quantity=4" -d "payment_method=card")
BCODE=$(echo "$L" | grep -oP '(?<=mock-pay/)[A-Z0-9]+')
chk "4 pending after checkout start" "$(stat $RID tickets_pending)" "4"
C=$($CURL -o /dev/null -w "%{http_code}" $B/cancelled/$BCODE)
chk "cancel page loads" "$C" "200"
chk "pending released" "$(stat $RID tickets_pending)" "0"
chk "pool unchanged" "$(stat $RID tickets_sold)" "15"

echo
echo "=============================================="
echo "14. Validation"
echo "=============================================="
C=$($CURL -o /dev/null -w "%{http_code}" -X POST $B/buy -d "raffle_id=$RID" -d "name=" -d "quantity=1")
chk "empty name rejected" "$C" "400"
C=$($CURL -o /dev/null -w "%{http_code}" -X POST $B/buy -d "raffle_id=$RID" -d "name=X" -d "email=x@e2e.com" -d "phone=7705550009" -d "quantity=0")
chk "qty 0 rejected" "$C" "400"
C=$($CURL -o /dev/null -w "%{http_code}" -X POST $B/buy \
  -d "raffle_id=$RID" -d "name=X" -d "email=x@e2e.com" -d "phone=7705550009" -d "quantity=1" -d "payment_method=bitcoin")
chk "unknown method rejected" "$C" "400"
C=$($CURL -o /dev/null -w "%{http_code}" $B/raffle/9999)
chk "missing raffle 404s" "$C" "404"

echo
echo "=============================================="
echo "16. GIVEAWAY -- free event tickets"
echo "=============================================="
BEFORE_R=$(stat $RID revenue)
BEFORE_T=$(stat $RID tickets_sold)
L=$($CURL -o /dev/null -w "%{redirect_url}" -X POST $B/admin/$RID/giveaway \
  -d "name=Event Erin" -d "email=erin@e2e.com" -d "quantity=6" -d "note=Booth demo")
echo "  -> $L"
echo "$L" | grep -q "/giveaway/" && ok "routed to giveaway slip" || no "wrong route"
GC=$(echo "$L" | grep -oP '(?<=/giveaway/)[A-Z0-9]+')
AFTER_T=$(stat $RID tickets_sold)
chk "6 tickets added to pool" "$AFTER_T" "$((BEFORE_T + 6))"
chk "revenue UNCHANGED (free)" "$(stat $RID revenue)" "$BEFORE_R"
chk "no pending (active immediately)" "$(stat $RID tickets_pending)" "0"
chk "comp counter = 6" "$(stat $RID tickets_comp)" "6"

SLIP=$($CURL $B/giveaway/$GC)
echo "$SLIP" | grep -q "Free Giveaway Ticket" && ok "slip header" || no "no header"
echo "$SLIP" | grep -q "Event Erin" && ok "recipient shown" || no "no recipient"
echo "$SLIP" | grep -q "No purchase necessary" && ok "disclaimer present" || no "no disclaimer"
echo "$SLIP" | grep -q "chance to win" && ok "shows live odds" || no "no odds"

echo
echo "=============================================="
echo ""
echo "=============================================="
echo "16b. REQUIRED FIELDS -- email + phone"
echo "=============================================="
C=$($CURL -o /dev/null -w "%{http_code}" -X POST $B/buy \
  -d "raffle_id=$RID" -d "name=No Phone" -d "email=np@e2e.com" -d "quantity=1")
chk "donate without phone rejected 400" "$C" "400"

C=$($CURL -o /dev/null -w "%{http_code}" -X POST $B/buy \
  -d "raffle_id=$RID" -d "name=Short Phone" -d "email=sp@e2e.com" \
  -d "phone=555" -d "quantity=1")
chk "donate with 3-digit phone rejected 400" "$C" "400"

C=$($CURL -o /dev/null -w "%{http_code}" -X POST $B/buy \
  -d "raffle_id=$RID" -d "name=No Email" -d "phone=7705551111" -d "quantity=1")
chk "donate without email rejected 400" "$C" "400"

C=$($CURL -o /dev/null -w "%{http_code}" -X POST $B/buy \
  -d "raffle_id=$RID" -d "name=Bad Email" -d "email=nope" \
  -d "phone=7705551111" -d "quantity=1")
chk "donate with malformed email rejected 400" "$C" "400"

# address is NOT required on the donated path -- nothing to mail back
C=$($CURL -o /dev/null -w "%{http_code}" -X POST $B/buy \
  -d "raffle_id=$RID" -d "name=Valid NoAddr" -d "email=vna@e2e.com" \
  -d "phone=(770) 555-2222" -d "quantity=1" -d "payment_method=cash")
chk "donate without address ACCEPTED 303" "$C" "303"

# mail-in AMOE: address IS required
L=$($CURL -o /dev/null -w "%{redirect_url}" -X POST $B/admin/$RID/mailin \
  -d "name=Mail NoAddr" -d "email=mna@e2e.com" -d "phone=7705553333" \
  -d "postmark=2026-01-01")
echo "$L" | grep -q "mailin/" && ok "mail-in without address ACCEPTED (optional)" \
  || no "mail-in without address rejected -- address should be optional"

L=$($CURL -o /dev/null -w "%{redirect_url}" -X POST $B/admin/$RID/mailin \
  -d "name=Mail NoPhone" -d "email=mnp@e2e.com" \
  -d "address=99 Real St, Atlanta GA 30341" -d "postmark=2026-01-01")
echo "$L" | grep -q "err=" && ok "mail-in without phone rejected" \
  || no "mail-in without phone was ACCEPTED -- BUG"

L=$($CURL -o /dev/null -w "%{redirect_url}" -X POST $B/admin/$RID/mailin \
  -d "name=Mail Valid" -d "email=mv@e2e.com" -d "phone=770-555-4444" \
  -d "address=99 Real Street, Atlanta GA 30341" -d "postmark=2026-01-01")
echo "$L" | grep -q "mailin/" && ok "mail-in with full details accepted" \
  || no "mail-in with full details rejected -- BUG"

echo "17. SECURITY -- public cannot self-issue free tickets"
echo "=============================================="
C=$($CURL -o /dev/null -w "%{http_code}" -X POST $B/buy \
  -d "raffle_id=$RID" -d "name=Cheater Chuck" -d "email=chuck@e2e.com" \
  -d "phone=7705550500" -d "quantity=500" -d "payment_method=comp")
chk "public comp POST rejected 403" "$C" "403"
BP=$($CURL $B/raffle/$RID)
echo "$BP" | grep -q "Free Giveaway" && no "comp EXPOSED on buy page -- BUG" || ok "comp hidden from buy page"
M=$($CURL $B/api/methods)
echo "$M" | grep -q '"comp"' && no "comp leaked via API -- BUG" || ok "comp not in public API"

echo
echo "=============================================="
echo "18. Drum marks giveaway tickets"
echo "=============================================="
CSV=$($CURL $B/admin/$RID/drum.csv)
echo "$CSV" | head -1 | grep -q "type" && ok "CSV has type column" || no "no type column"
NG=$(echo "$CSV" | grep -c "GIVEAWAY")
chk "6 GIVEAWAY rows in CSV" "$NG" "6"
D=$($CURL $B/admin/$RID/drum)
echo "$D" | grep -q "badge comp" && ok "drum page flags free tickets" || no "no flag on drum"

echo
echo "=============================================="
echo "19. Draw uses only paid tickets"
echo "=============================================="
C=$($CURL -o /dev/null -w "%{http_code}" -X POST $B/admin/$RID/draw)
chk "draw redirects" "$C" "303"
W=$($CURL $B/admin/$RID/winners)
NW=$(echo "$W" | grep -oP '(?<=<td><b>)[^<]+' | wc -l)
chk "4 winners" "$NW" "4"
echo "$W" | grep -q "Pending Pat" && no "REJECTED buyer won -- BUG" || ok "rejected buyer cannot win"
echo "$W" | grep -q "Bail Bob" && no "CANCELLED buyer won -- BUG" || ok "cancelled buyer cannot win"

echo
echo "=============================================="
echo "RESULTS: $P passed, $F failed"
echo "=============================================="
[ $F -eq 0 ] || exit 1
