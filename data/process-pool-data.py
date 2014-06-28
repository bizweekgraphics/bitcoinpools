import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import json
import urllib2

pd.set_option('display.mpl_style', 'default') # Make the graphs a bit prettier
plt.rcParams['figure.figsize'] = (15, 5)


rawBlocksWeekly = pd.read_csv('weeklyBlockSolves.csv', parse_dates=['Date'])
rawBlocksDaily = pd.read_csv('dailyBlockSolves.csv', parse_dates=['Date'])

rawBlocksWeekly = rawBlocksWeekly.drop('Unnamed: 0', 1).rename(columns=
                                                           {'Date': 'date',
                                                            'Pool': 'pool',
                                                            'Number of Blocks': 'blocks',
                                                            'Percentage of Blocks': 'percentage'})

rawBlocksDaily = rawBlocksDaily.drop('Unnamed: 0', 1).rename(columns=
                                                           {'Date': 'date',
                                                            'Pool': 'pool',
                                                            'Number of Blocks': 'blocks',
                                                            'Percentage of Blocks': 'percentage'})

blocksFrame = rawBlocksWeekly

# (OVER)SPECIFIC LITTLE CLEANING ITEMS

# Remove dates where percentages total < 99%.
# Last I checked there was only one such bad day: 2011-02-27.
# But hey, written for generality:
datesums = blocksFrame.groupby('date').sum()
badDays = datesums[datesums['percentage'] < 99].index.values
for badDay in badDays:
    blocksFrame = blocksFrame[blocksFrame['date'] != badDay]
# That leaves a gap so we reindex.
blocksFrame = blocksFrame.reset_index(drop=True)

# INTERPOLATION OF DAILY DATA ("ADAPTIVE RESAMPLING")

# Find three largest pools
topPools = blocksFrame.groupby('pool').max().sort('percentage', ascending=0)  #sort by max percentage
topPools = topPools.loc[topPools.index != "Unknown"]                          #filter out Unknown
topPools = topPools[:3]                                                       #take top 3

# For each of the three largest pools...
for topPool in topPools.transpose().iteritems():
    poolName = topPool[0]
    # find date on which pool hit peak network share (percentage)
    poolMaxDate = rawBlocksDaily.iloc[rawBlocksDaily[rawBlocksDaily['pool'] == poolName]['percentage'].idxmax()]['date']
    # and append the data for that date
    blocksFrame = blocksFrame.append(rawBlocksDaily[rawBlocksDaily['date'] == poolMaxDate])

# Append the latest daily data (which is apt to be more recent than the latest weekly)
dailyMaxDate = rawBlocksDaily.iloc[rawBlocksDaily['date'].idxmax()]['date']
blocksFrame = blocksFrame.append(rawBlocksDaily[rawBlocksDaily['date'] == dailyMaxDate])

# I was getting an out-of-bounds error on dateMax below, so I reindex, which seems to work...
blocksFrame = blocksFrame.reset_index(drop=True)

# Get first and last days of pool block data (will be interval for prices)
dateMin = blocksFrame.iloc[blocksFrame['date'].idxmin()]['date'].strftime('%Y-%m-%d')
dateMax = blocksFrame.iloc[blocksFrame['date'].idxmax()]['date'].strftime('%Y-%m-%d')

# API only supports 2010-07-17 and later.
coindeskMin = '2010-07-17'
dateMin = dateMin if dateMin > coindeskMin else coindeskMin

# Fetching historical prices from Coindesk. API docs at http://www.coindesk.com/api/
url = 'http://api.coindesk.com/v1/bpi/historical/close.json?start='+dateMin+'&end='+dateMax
response = urllib2.urlopen(url)
pricesJSON = response.read()
prices = json.loads(pricesJSON)['bpi']

datesAndPrices = []
for x,y in prices.iteritems():
    datesAndPrices.append({'date': x, 'price': y})

datesAndPrices = sorted(datesAndPrices, key=lambda datesAndPrices: datesAndPrices['date'])

# Nest raw blocks
pools = blocksFrame.groupby('pool').groups.keys()
dates = blocksFrame.groupby('date').groups.keys()

# Get aggregate statistics
poolMax = blocksFrame.groupby('pool').max()[['percentage']].rename(columns={'percentage':'maxPercentage'})
poolSum = blocksFrame.groupby('pool').sum()[['blocks']].rename(columns={'blocks':'sumBlocks'})
poolStats = poolMax.join(poolSum)

# Build an array of dictionaries fit for our eventual charting purposes
blocksByPool = []
for name, stats in poolStats.transpose().to_dict().iteritems():
    values = []

    for date in dates:

        # numpy date objects will be written to json as %Y-%m-%d
        dateString = pd.to_datetime(str(date)).strftime('%Y-%m-%d')

        results = blocksFrame[(blocksFrame['pool'] == name) & (blocksFrame['date'] == date)]
        if len(results) == 0:
            values.append(
                {'date': dateString,
                 'percentage': 0,
                 'blocks': 0,
                 'price': 0,
                 'reward': 0,
                 'revenue': 0,
                 'periodDays': 7 })
        else:

            # Cf. https://bitcoinfoundation.org/2012/11/28/happy-halving-day/
            # Since this is just working off weekly data, revenue estimates for that week may be off!!!
            halvingday = np.datetime64('2012-11-28 15:24:38Z')
            reward = 50 if dates[9] < halvingday else 25

            # Fetch Bitcoin Coindesk Price Index (BPI) for date. Cf. www.coindesk.com/api/
            price = prices[dateString] if dateString in prices else 0

            values.append(
                {'date': dateString,
                 'percentage': results[['percentage']].values[0][0]/100,
                 'blocks': results[['blocks']].values[0][0],
                 'revenue': results[['blocks']].values[0][0] * price * reward,
                 'periodDays': 7 })

    blocksByPool.append(
        {'name': name,
         'maxPercentage': stats['maxPercentage']/100,
         'sumBlocks': stats['sumBlocks'],
         'values': values})

data = {'pools': blocksByPool,
        'dates': datesAndPrices,
        'sources':
            [{ 'name': 'Organ of Corti',
               'data': 'Block mining data',
               'url': 'http://organofcorti.blogspot.com/',
               'file': False,
               'fileType': False },
             { 'name': 'Coindesk',
               'data': 'Bitcoin price data',
               'url': 'http://coindesk.com/api',
               'file': url,
               'fileType': 'json' }],
        'colophon': "Data is derived from claims made by miners, either on their websites or in coinbase signatures, and known addresses. Due to the anonymous nature of the Bitcoin network, mining (in the form of block solves) is only identifiable if declared, and even then is not verifiable. Notably, Slush's pool was the first in operation (in December 2010), but data for it only became available in January 2012. Data is weekly except for the three weeks when DeepBit, BTC Guild, and GHash.IO peaked, during which daily data is shown; thus, those jagged spans indicate higher-resolution data, not necessarily higher intrinsic volatility. Inferred network share percentages are subject to fluctuations due to luck; e.g., over a ten-minute period, there may be only one miner to successfully mine a block, but one should not infer an instantaneous network share of 100%. Furthermore, there is no guarantee that your sense perceptions correspond to an objective reality, or indeed that a world exists outside your head.",
        'credits': {'author': 'Toph Tucker'}
        }

with open('data.json', 'w') as outfile:
  json.dump(data, outfile)
