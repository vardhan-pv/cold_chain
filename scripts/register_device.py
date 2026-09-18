import argparse,json,os
from getpass import getpass
import httpx

def main():
    p=argparse.ArgumentParser();p.add_argument('--id',required=True);p.add_argument('--name',default='Cold chain unit')
    p.add_argument('--mode',choices=['SIMULATION','HARDWARE'],required=True);p.add_argument('--url',default='http://127.0.0.1:8000')
    args=p.parse_args();token=os.getenv('CC_ADMIN_TOKEN') or getpass('Operator token: ')
    with httpx.Client(timeout=10) as client:
        r=client.post(args.url+'/api/devices',headers={'Authorization':'Bearer '+token},
            json={'device_id':args.id,'name':args.name,'mode':args.mode})
        r.raise_for_status();data=r.json()
    print(json.dumps(data,indent=2))
    print('Store device_token privately. It is only returned at registration; never commit it.')

if __name__=='__main__':main()
