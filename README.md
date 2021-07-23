# esme\_local

Run Earth System Model runs using esme on the local machine.

## Install

Please make sure you have a clean shell with no conda/pip environments activated and no modules loaded.

```
git clone git@github.com:ClimateIT/esme_local.git
cd esme_local
./install.sh
```


## Run an experiment

```
source activate.sh
python esme.py create --name pm-04 --template wrf_cmaq_policy_mode
python esme.py setup --name pm-04
python esme.py run --name pm-04
```

