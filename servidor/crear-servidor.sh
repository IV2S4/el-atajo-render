#!/bin/bash
# AUTONOMON - crea el servidor gratis (Always Free) en Oracle Cloud.
# Se ejecuta en Oracle Cloud Shell:
#   curl -sL https://raw.githubusercontent.com/IV2S4/el-atajo-render/main/servidor/crear-servidor.sh | bash
set -e
C="${OCI_TENANCY:?No encuentro OCI_TENANCY (¿estás en Cloud Shell?)}"
N=autonomon
q() { oci "$@" 2>/dev/null; }
say() { echo -e "\n>>> $*"; }

[ -f ~/.ssh/id_rsa ] || ssh-keygen -t rsa -b 4096 -N "" -f ~/.ssh/id_rsa -q
curl -sL https://raw.githubusercontent.com/IV2S4/el-atajo-render/main/servidor/instalar-n8n.sh -o ~/instalar-n8n.sh

say "1/5 Red (VCN)"
VCN=$(q network vcn list -c "$C" --display-name $N-vcn --query 'data[0].id' --raw-output || true)
if [ -z "$VCN" ] || [ "$VCN" = "None" ] || [ "$VCN" = "null" ]; then
  VCN=$(oci network vcn create -c "$C" --cidr-block 10.0.0.0/16 --display-name $N-vcn --dns-label autonomon \
        --wait-for-state AVAILABLE --query data.id --raw-output)
fi
echo "VCN: $VCN"

say "2/5 Salida a internet"
IGW=$(q network internet-gateway list -c "$C" --vcn-id "$VCN" --query 'data[0].id' --raw-output || true)
if [ -z "$IGW" ] || [ "$IGW" = "None" ] || [ "$IGW" = "null" ]; then
  IGW=$(oci network internet-gateway create -c "$C" --vcn-id "$VCN" --is-enabled true --display-name $N-igw \
        --wait-for-state AVAILABLE --query data.id --raw-output)
fi
RT=$(oci network vcn get --vcn-id "$VCN" --query 'data."default-route-table-id"' --raw-output)
oci network route-table update --rt-id "$RT" --force \
  --route-rules "[{\"destination\":\"0.0.0.0/0\",\"destinationType\":\"CIDR_BLOCK\",\"networkEntityId\":\"$IGW\"}]" >/dev/null

say "3/5 Puertas abiertas (22, 80, 443)"
SL=$(oci network vcn get --vcn-id "$VCN" --query 'data."default-security-list-id"' --raw-output)
oci network security-list update --security-list-id "$SL" --force \
  --egress-security-rules '[{"destination":"0.0.0.0/0","protocol":"all","isStateless":false}]' \
  --ingress-security-rules '[
    {"source":"0.0.0.0/0","protocol":"6","isStateless":false,"tcpOptions":{"destinationPortRange":{"min":22,"max":22}}},
    {"source":"0.0.0.0/0","protocol":"6","isStateless":false,"tcpOptions":{"destinationPortRange":{"min":80,"max":80}}},
    {"source":"0.0.0.0/0","protocol":"6","isStateless":false,"tcpOptions":{"destinationPortRange":{"min":443,"max":443}}},
    {"source":"0.0.0.0/0","protocol":"1","isStateless":false,"icmpOptions":{"type":3,"code":4}}]' >/dev/null

SUB=$(q network subnet list -c "$C" --vcn-id "$VCN" --query 'data[0].id' --raw-output || true)
if [ -z "$SUB" ] || [ "$SUB" = "None" ] || [ "$SUB" = "null" ]; then
  SUB=$(oci network subnet create -c "$C" --vcn-id "$VCN" --cidr-block 10.0.1.0/24 --display-name $N-subnet \
        --dns-label pub --route-table-id "$RT" --security-list-ids "[\"$SL\"]" \
        --wait-for-state AVAILABLE --query data.id --raw-output)
fi
echo "Subnet: $SUB"

say "4/5 Creando el servidor (puede tardar unos minutos)"
EXIST=$(q compute instance list -c "$C" --display-name $N --lifecycle-state RUNNING --query 'data[0].id' --raw-output || true)
ID=""
if [ -n "$EXIST" ] && [ "$EXIST" != "None" ] && [ "$EXIST" != "null" ]; then
  ID=$EXIST; echo "Ya existe: $ID"
else
  ADS=$(oci iam availability-domain list -c "$C" --query 'data[].name' --raw-output | tr -d '[]", ' | grep -v '^$')
  intentar() {  # $1 shape  $2 config  $3 image
    for AD in $ADS; do
      echo "Probando $1 en $AD..."
      ID=$(oci compute instance launch -c "$C" --availability-domain "$AD" --display-name $N \
        --shape "$1" $2 --image-id "$3" --subnet-id "$SUB" --assign-public-ip true \
        --boot-volume-size-in-gbs 50 --ssh-authorized-keys-file ~/.ssh/id_rsa.pub \
        --user-data-file ~/instalar-n8n.sh --wait-for-state RUNNING --max-wait-seconds 900 \
        --query data.id --raw-output 2>/tmp/err.txt) && return 0
      grep -o '"message": "[^"]*"' /tmp/err.txt | head -1
    done
    return 1
  }
  IMG_ARM=$(oci compute image list -c "$C" --operating-system "Canonical Ubuntu" --operating-system-version "24.04" \
            --shape VM.Standard.A1.Flex --sort-by TIMECREATED --query 'data[0].id' --raw-output)
  if ! intentar VM.Standard.A1.Flex '--shape-config {"ocpus":2,"memoryInGBs":12}' "$IMG_ARM"; then
    echo "No hay espacio para el servidor grande (ARM). Uso el pequeño gratis (AMD)."
    IMG_X86=$(oci compute image list -c "$C" --operating-system "Canonical Ubuntu" --operating-system-version "24.04" \
              --shape VM.Standard.E2.1.Micro --sort-by TIMECREATED --query 'data[0].id' --raw-output)
    intentar VM.Standard.E2.1.Micro "" "$IMG_X86" || { echo "ERROR: no se pudo crear el servidor"; cat /tmp/err.txt; exit 1; }
  fi
fi

say "5/5 Datos del servidor"
IP=$(oci compute instance list-vnics --instance-id "$ID" --query 'data[0]."public-ip"' --raw-output)
echo "$IP" > ~/autonomon-ip.txt
echo "IP=$IP"
echo "URL=https://${IP//./-}.sslip.io"
echo "Instalando n8n adentro (5-8 min). Revisa con: ssh ubuntu@$IP cat /opt/autonomon/estado"
