# Mini SOC — path /home/atok/home/soc_dev

## Extract / copy files
Pastikan semua file ini berada di:

    /home/atok/home/soc_dev

## Jalankan

```bash
cd /home/atok/home/soc_dev
bash fix_restart_stack.sh
```

## Jika first deploy

```bash
cd /home/atok/home/soc_dev
bash setup_mini_soc.sh
```

## Inject test data

```bash
cd /home/atok/home/soc_dev
bash diagnose_and_inject.sh
```

## Akses
- Grafana: http://localhost:3000
- user: admin
- pass: minisoc2026

## Cek semua service berjalan
sudo docker network inspect soc_project_soc-net | python3 -c "import sys,json; d=json.load(sys.stdin)[0]; print('Bridge:', d.get('Options',{}).get('com.docker.network.bridge.name','not-set')); [print(f'  {v[\"Name\"]}: {v[\"IPv4Address\"]}') for v in d['Containers'].values()]"