#!/bin/bash
# AUTONOMON - crea el servidor gratis (Always Free) en Oracle Cloud.
# Se ejecuta en Oracle Cloud Shell:
#   curl -sLo s.sh https://raw.githubusercontent.com/IV2S4/el-atajo-render/main/servidor/crear-servidor.sh ; bash s.sh
# Reintenta solo si Oracle dice "Out of host capacity" (pasa seguido con el servidor gratis ARM).
C="${OCI_TENANCY:?No encuentro OCI_TENANCY (¿estás en Cloud Shell?)}"
N=autonomon
RONDAS="${RONDAS:-40}"
ok() { [ -n "$1" ] && [ "$1" != "None" ] && [ "$1" != "null" ]; }
say() { echo -e "\n>>> $*"; }

[ -f ~/.ssh/id_rsa ] || ssh-keygen -t rsa -b 4096 -N "" -f ~/.ssh/id_rsa -q
curl -sL https://raw.githubusercontent.com/IV2S4/el-atajo-render/main/servidor/instalar-n8n.sh -o ~/instalar-n8n.sh

say "1/5 Red"
VCN=$(oci network vcn list -c "$C" --display-name $N-vcn --query 'data[0].id' --raw-output 2>/dev/null)
ok "$VCN" || VCN=$(oci network vcn create -c "$C" --cidr-block 10.0.0.0/16 --display-name $N-vcn --dns-label autonomon \
        --wait-for-state AVAILABLE --query data.id --raw-output)
IGW=$(oci network internet-gateway list -c "$C" --vcn-id "$VCN" --query 'data[0].id' --raw-output 2>/dev/null)
ok "$IGW" || IGW=$(oci network internet-gateway create -c "$C" --vcn-id "$VCN" --is-enabled true --display-name $N-igw \
        --wait-for-state AVAILABLE --query data.id --raw-output)
RT=$(oci network vcn get --vcn-id "$VCN" --query 'data."default-route-table-id"' --raw-output)
oci network route-table update --rt-id "$RT" --force \
  --route-rules "[{\"destination\":\"0.0.0.0/0\",\"destinationType\":\"CIDR_BLOCK\",\"networkEntityId\":\"$IGW\"}]" >/dev/null
SL=$(oci network vcn get --vcn-id "$VCN" --query 'data."default-security-list-id"' --raw-output)
oci network security-list update --security-list-id "$SL" --force \
  --egress-security-rules '[{"destination":"0.0.0.0/0","protocol":"all","isStateless":false}]' \
  --ingress-security-rules '[
    {"source":"0.0.0.0/0","protocol":"6","isStateless":false,"tcpOptions":{"destinationPortRange":{"min":22,"max":22}}},
    {"source":"0.0.0.0/0","protocol":"6","isStateless":false,"tcpOptions":{"destinationPortRange":{"min":80,"max":80}}},
    {"source":"0.0.0.0/0","protocol":"6","isStateless":false,"tcpOptions":{"destinationPortRange":{"min":443,"max":443}}},
    {"source":"0.0.0.0/0","protocol":"1","isStateless":false,"icmpOptions":{"type":3,"code":4}}]' >/dev/null
SUB=$(oci network subnet list -c "$C" --vcn-id "$VCN" --query 'data[0].id' --raw-output 2>/dev/null)
ok "$SUB" || SUB=$(oci network subnet create -c "$C" --vcn-id "$VCN" --cidr-block 10.0.1.0/24 --display-name $N-subnet \
        --dns-label pub --route-table-id "$RT" --security-list-ids "[\"$SL\"]" \
        --wait-for-state AVAILABLE --query data.id --raw-output)
echo "Red lista."

say "2/5 ¿Qué servidores gratis hay en cada zona?"
ADS=$(oci iam availability-domain list -c "$C" --query 'data[].name' --raw-output | tr -d '[]", ' | grep -v '^$')
declare -A MICRO
for AD in $ADS; do
  S=$(oci compute shape list -c "$C" --availability-domain "$AD" --all --query 'data[].shape' --raw-output 2>/dev/null | tr -d '[]", ')
  echo "$AD: $(echo "$S" | grep -e A1.Flex -e E2.1.Micro | tr '\n' ' ')"
  echo "$S" | grep -q E2.1.Micro && MICRO[$AD]=1
done
IMG_ARM=$(oci compute image list -c "$C" --operating-system "Canonical Ubuntu" --operating-system-version "24.04" \
          --shape VM.Standard.A1.Flex --sort-by TIMECREATED --query 'data[0].id' --raw-output)
IMG_X86=$(oci compute image list -c "$C" --operating-system "Canonical Ubuntu" --operating-system-version "24.04" \
          --shape VM.Standard.E2.1.Micro --sort-by TIMECREATED --query 'data[0].id' --raw-output)
ok "$IMG_X86" || IMG_X86=$(oci compute image list -c "$C" --operating-system "Canonical Ubuntu" \
          --shape VM.Standard.E2.1.Micro --sort-by TIMECREATED --query 'data[0].id' --raw-output)
echo "Imagen ARM: ${IMG_ARM: -12}  Imagen AMD: ${IMG_X86: -12}"

lanzar() {  # $1 AD  $2 shape  $3 config  $4 image
  oci compute instance launch -c "$C" --availability-domain "$1" --display-name $N \
    --shape "$2" $3 --image-id "$4" --subnet-id "$SUB" --assign-public-ip true \
    --boot-volume-size-in-gbs 50 --ssh-authorized-keys-file ~/.ssh/id_rsa.pub \
    --user-data-file ~/instalar-n8n.sh --query data.id --raw-output 2>/tmp/err.txt
}
motivo() { grep -o '"message": "[^"]*"' /tmp/err.txt | head -1; }

say "3/5 Creando el servidor"
ID=$(oci compute instance list -c "$C" --display-name $N --query "data[?\"lifecycle-state\"!='TERMINATED'] | [0].id" --raw-output 2>/dev/null)
if ok "$ID"; then echo "Ya existe: $ID"; fi
R=1
while ! ok "$ID" && [ $R -le $RONDAS ]; do
  echo "--- Intento $R de $RONDAS ($(date +%H:%M)) ---"
  for AD in $ADS; do
    for CFG in '{"ocpus":2,"memoryInGBs":12}' '{"ocpus":1,"memoryInGBs":6}'; do
      ID=$(lanzar "$AD" VM.Standard.A1.Flex "--shape-config $CFG" "$IMG_ARM") && break 2
      echo "ARM $CFG en ${AD##*-AD-}: $(motivo)"
    done
  done
  if ! ok "$ID"; then
    for AD in $ADS; do
      [ -n "${MICRO[$AD]}" ] || continue
      ID=$(lanzar "$AD" VM.Standard.E2.1.Micro "" "$IMG_X86") && break
      echo "AMD micro en ${AD##*-AD-}: $(motivo)"
    done
  fi
  ok "$ID" && break
  R=$((R+1)); sleep 60
done
ok "$ID" || { echo "No hubo espacio después de $RONDAS intentos. Vuelve a correr: bash s.sh"; exit 1; }

say "4/5 Esperando que arranque"
oci compute instance get --instance-id "$ID" --wait-for-state RUNNING --max-wait-seconds 900 >/dev/null
SHAPE=$(oci compute instance get --instance-id "$ID" --query 'data.shape' --raw-output)

say "5/5 Datos del servidor"
IP=$(oci compute instance list-vnics --instance-id "$ID" --query 'data[0]."public-ip"' --raw-output)
echo "$IP" > ~/autonomon-ip.txt
echo "TIPO=$SHAPE"
echo "IP=$IP"
echo "URL=https://${IP//./-}.sslip.io"
echo "Instalando n8n adentro (5-10 min). Revisa con: ssh -o StrictHostKeyChecking=no ubuntu@$IP cat /opt/autonomon/estado"
