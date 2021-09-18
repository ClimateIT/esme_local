# esme\_local

Run Earth System Model runs using esme on the local machine.

## Install

Please make sure you have a clean shell with no conda/pip environments activated and no modules loaded.

```
git clone git@github.com:ClimateIT/esme_local.git
cd esme_local
./install.sh
```

## Run a Policy Mode experiment

```
source activate.sh
python esme.py create --name pm-04 --template wrf_cmaq_policy_mode
python esme.py setup --name pm-04
python esme.py run --name pm-04
```

## Run a WRF-CMAQ forecast

The forecast template is currently setup to start at `{{yesterday}}T06` (i.e. yesterday at 6 am UTC).

```
source activate.sh
python esme.py create --name forecast-01 --template wrf_cmaq_forecast
python esme.py setup --name forecast-01
python esme.py run --name forecast-01
```

## Update software

To update ESME:

```
cd esme_local
git pull
source activate.sh
conda env update --file conda_env.yaml --prune
```

Then for any (incomplete) experiments that may need new fixes:

```
cd <exp_id>
git checkout esme-main
git pull
git submodule update
```

Now re-run `setup` for any (incomplete) experiments that may need new fixes:

```
cd esme_local
python esme.py setup --name <exp_id>
```
