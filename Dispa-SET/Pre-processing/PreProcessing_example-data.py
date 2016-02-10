'''
 This script is the Python pre-processing tool for the JRC Dispa-SET 2.0 model
 The output is a gdx file readable in GAMS
 It requires the DispaSET_io_data.py utility, developed by S. Quoilin and the gdxx.py utility, provided in GAMS
 To install the gdxx library (for Python 2.7):
 C:\GAMS\win64\24.0\apifiles\Python\api>python gdxsetup.py install

changes in 2.1: modification of variables: demand, costvariable, fuelprice, flowmacimum, flowminimum,markup,pricetransmission
changes in 2.1.1: set and parameters are now stored in dictionnaries instead of a list

'''

__author__ = 'Sylvain Quoilin <sylvain.quoilin@ec.europa.eu>'


import sys
sys.path.append('../python-files')

from DispaSET_io_data import write_toexcel,write_variables
from DispaTools import load_csv_to_pd,clustering
import pandas as pd
import numpy as np
import os
import shutil
import matplotlib.pyplot as plt


###################################################################################################################
#####################################   Main Inputs    ############################################################
###################################################################################################################

# Paths:
gams_dir = '/home/sylvain/progs/GAMS/matlab'
#gams_dir = 'C:\\GAMS\\win64\\24.3'

path_data_csv = 'example-data/csv'
path_data_pandas = 'example-data/pandas'

# Create simulation test case environment:
# Provide the path of the folder to be created. Leave empty if no simulation environment should be created.

sim = '../Simulation'

description = '6.3 GW storage, only 2 hours capacity, pumped hydro into reserve'

# Formats to write final template of inputs:
# gdx is required for GAMS, excel allows visualizing the data, pickle is the fastest solution
write_excel = True
write_gdx = True
write_pickle = True

# Residual binary variable:
# if True, no power is assigned to VRE, VRE production is deducted from the load
# if False, the total load is provided to Dispaset, VRE are considered as must-run power plants (but with some curtailment allowed)
use_residual_load = False

# additional VRE, storage and demand (set Pcap to -1 to use historical values):
hours_sto = 4                           # Number of hours of storage at full capacity
coeff_charge = 1                        # Load scaling factor
SheddingCapacity = 331                  # Interruptible load contracts
CO2Price = 7                            # ETS (EUR/MWh)
StorageEfficiency = 0.75                # round trip efficiency

# Day/hour corresponding to the first line of the data:
y_start = 2012
m_start = 10
d_start = 1
h_start = 0    # Hours are defined from 0 to 23

# Number of hours to be simulated:
Ndays = 9
Nhours = 24*Ndays

# Cropping interval: DispaSET can be instructed to simulate only a subset of the provided data
# These parameters define the number of days to crop at the beginning and at the end. 
# Set to 0 to simulate the whole period.
cropping_beginning = 0
cropping_end = 0

# Length and look ahead period of rolling horizon (in days):
RollingHorizon_length = 3
RollingHorizon_lookahead = 1

# boolean option to merge plants or not
merge_plants = True

# Allow Curtailment:
curtailment=True


###################################################################################################################
#####################################   Data Loading    ###########################################################
###################################################################################################################

# Load plant data:
plants = load_csv_to_pd(path_data_csv,'Production_park_data.csv',path_data_pandas,'Production_park_data').set_index('Index')

# Load demand data:
load_data_pd_z1 = load_csv_to_pd(path_data_csv,'load_data_z1.csv',path_data_pandas,'load_data_z1')
load_data_z1 = np.array(load_data_pd_z1['Vertical load [kW]'])

load_data_pd_z2 = load_csv_to_pd(path_data_csv,'load_data_z2.csv',path_data_pandas,'load_data_z2')
load_data_z2 = np.array(load_data_pd_z2['Vertical load [kW]'])

# Outage data:
outages_pd = load_csv_to_pd(path_data_csv,'outages.csv',path_data_pandas,'outages')
outages= np.array(outages_pd)[:,1:]

# Load the timestamps in string format:
dates_pd = load_csv_to_pd(path_data_csv,'daysofyear.csv',path_data_pandas,'daysofyear')
dates= dates_pd.Date.tolist()

# Load the historical generation data:
generation_data_pd = load_csv_to_pd(path_data_csv,'generation_data.csv',path_data_pandas,'generation_data')
generation_data= np.array(generation_data_pd)

# Load interconnections
inter_z1_pd = load_csv_to_pd(path_data_csv,'interconnections_z1.csv',path_data_pandas,'interconnections_z1')
inter_z2_pd = load_csv_to_pd(path_data_csv,'interconnections_z2.csv',path_data_pandas,'interconnections_z2')
interconnections = {'z1':np.array(inter_z1_pd['Power exchange']),'z2':np.array(inter_z2_pd['Power exchange'])}

# Load solar data:
solar_data_pd = load_csv_to_pd(path_data_csv,'solar_data.csv',path_data_pandas,'solar_data')
solar_data= np.array(solar_data_pd)

# Load wind data:
wind_data_pd = load_csv_to_pd(path_data_csv,'WindData.csv',path_data_pandas,'WindData')
wind_data= np.array(wind_data_pd)

# Fuel price data from IEA, monthly, in eur/MWhth
# From october 2012 to september 2013
price = {'coal_month':np.array([12.2430352051,12.2430352051,12.2430352051,10.2058479078,10.2058479078,10.2058479078,10.5107415473,10.5107415473,10.5107415473,9.8076194807,9.8076194807,9.8076194807])}
price['oil_month'] = np.array([73.7754656768,73.7754656768,73.7754656768,69.6732200066,69.6732200066,69.6732200066,67.2718323463,67.2718323463,67.2718323463,79.5365975377,79.5365975377,79.5365975377])
price['gas_month'] = np.array([28.85,28.85,28.85,30.05,30.05,30.05,29.9,29.9,29.9,30.2,30.2,30.2])



###################################################################################################################
#####################################   Data Formatting   #########################################################
###################################################################################################################

# In the dataset:
# 21 mars 2013: h=4105
# 21 June 2013: h = 7032
# 21 september: h= 8520
# 21 December: h = 1945

Nunits = len(plants)

# Calculating the starting row and hour:
# Find the starting row:
str_query = '(year == ' + str(y_start) + ') & (month == ' + str(m_start) + ') & (day == ' + str(d_start) + ') & (hour == ' + str(h_start) + ')'
find_rows = load_data_pd_z1.query(str_query)
if len(find_rows)==0:
    print 'The specified starting date could not be found in the data'
else:
    row_start = find_rows.index.values[0]

hour_start = (row_start)/4 + 1
day_start = (hour_start - 1)/24 + 1
row_end = row_start + Nhours * 4

# Shrink outages to the considered days and turn into a list:
outages = outages[:,day_start-1:day_start + Ndays-1].tolist()

# Shrink the 15-min data to the considered period, convert kW to MW when necessary:
dates = dates[row_start:row_end]
generation_data = generation_data[row_start:row_end,:]/1000
load_data_z1 = load_data_z1[row_start:row_end]/1000
load_data_z2 = load_data_z2[row_start:row_end]/1000
interconnections['z1'] = interconnections['z1'][row_start:row_end]/1000
interconnections['z2'] = interconnections['z2'][row_start:row_end]/1000
solar_data = solar_data[row_start:row_end,:]
wind_data = wind_data[row_start:row_end,:]/1000

# Transforming the fuel price (monthly data) into hourly data:
xvals = np.linspace(1,12,8760)
price['oil_hour'] = np.interp(xvals,np.array(range(1,13)),price['oil_month'])
price['gas_hour'] = np.interp(xvals,np.array(range(1,13)),price['gas_month'])
price['coal_hour'] = np.interp(xvals,np.array(range(1,13)),price['coal_month'])
# shrink to the considered hours:
price['oil'] = price['oil_hour'][hour_start-1:hour_start+Nhours-1]
price['gas'] = price['gas_hour'][hour_start-1:hour_start+Nhours-1]
price['coal'] = price['coal_hour'][hour_start-1:hour_start+Nhours-1]

# Clustering power plants:
if merge_plants:
    [plants_merged,[outages_merged]]= clustering(plants,[np.array(outages)])
else:
    plants_merged = plants
    outages_merged = outages

# Storage variables:
# get the indexes of all storage units:
plants_sto = plants_merged[plants_merged['Technology']=='HUSTO']
Nsto = len(plants_sto)


###################################################################################################################
#####################################   Residual load     #########################################################
###################################################################################################################
# This section computes the Day-ahead net load and the actual net load
# The amount of VRE present in the system can be increased using by defining an additional installed power.

# Load
# The load can be defined in different ways, depending on the inclusion or not of VRE, interconnections, losses, etc.
# In this program, the following definitions is applied:
# load_tot: total Vertical load, i.e. the total consumption seen on the transmission network
# load_int: vertical load minus interconnections
# load_int_sol: vertical load minus interconnections and PV
# load_int_sol_wind: vertical load minus interc., PV and wind
# In the Elia load data, the non-monitored VRE is already substracted. It must therefore be added back.
# in the following, residual load is used for the load with additional VRE substracted.

# Historical installed capacity of VRE:
Pmax_sol = solar_data[:,4]
Pmax_wind = wind_data[:,2]

# PV generation:
solar_data[0:4451,0] = solar_data[0:4451,1]             # Day ahead values are not available for the first month, we take the morning predictions
AF_sol_15min = solar_data[:,2]/solar_data[:,4]          # Availability factor is obtained by dividing by the historical installed capacity of VRE:

#Psol_z1 = Pcap_sol_z1*AF_sol_15min
#Psol_z2 = Pcap_sol_z2*AF_sol_15min

# Wind generation
AF_wind_15min = wind_data[:,1]/wind_data[:,2]

#Pwind_z1 = Pcap_wind_z1*AF_wind_15min
#Pwind_z2 = Pcap_wind_z2*AF_wind_15min

# Water generation
# The water data include the hydro storage in turbine mode.
# To find the run-of-water production, the minimum production is taken for each day.
Pwater = generation_data[:,5]

for i in np.r_[0:len(Pwater):96]:
    P = np.sort(Pwater[i:i+95])
    P = np.minimum(P,80)            # P cannot be higher than the installed power
    P_mean = np.mean(P[1:4*4])    # taking the average of the 12 hours with less water generation
    Pwater[i:i+95]=P_mean
AF_water_temp = Pwater/80

# Non dispatchable plants:
P_nondispatch = 0
for i in plants_merged.index:
    if plants_merged['Technology'][i] in ['IS']:
        P_nondispatch = P_nondispatch + plants_merged['PowerCapacity'][i]
AF_nondispatch = 0.5 * np.ones(Nhours*4)                            # Hypothesis, in the absence of information...

# Transform 15-min data into hourly data:
demand_z1 = np.zeros([Nhours,1])
demand_z2 = np.zeros([Nhours,1])
AF_water = np.zeros(Nhours)
AF_wind = np.zeros(Nhours)
AF_sol = np.zeros(Nhours)
dates_h = []
dates_h_ymd = []
for i in range(Nhours):
    demand_z1[i] = np.mean(load_data_z1[1 + i*4 : (i+1)*4])
    demand_z2[i] = np.mean(load_data_z2[1 + i*4 : (i+1)*4])
    AF_water[i] = np.mean(AF_water_temp[1 + i*4 : (i+1)*4])
    AF_wind[i] = np.mean(AF_wind_15min[1 + i*4 : (i+1)*4])
    AF_sol[i] = np.mean(AF_sol_15min[1 + i*4 : (i+1)*4])
    dates_h.append(dates[i*4].encode('ascii','ignore'))
    dates_h_ymd.append(dates_h[i][1:12])


###################################################################################################################
#####################################   Reserve needs     #########################################################
###################################################################################################################

reserve_2U_tot = 500 * np.ones(Nhours)
reserve_2D_tot = 250 * np.ones(Nhours)


###################################################################################################################
############################################   Sets    ############################################################
###################################################################################################################


# In the case of a set, the uels variable must be a list containing the different set values
# In the case of a parameter, the 'sets' variable must be a list containing the different set dictionnaries
sets = {}
sets['h'] = [str(x+1) for x in range(Nhours)]
sets['d'] = [str(d+1) for d in range(Ndays)]
sets['mk'] = ['DA','2U','2D']
sets['n'] = ['Zone1','Zone2']
sets['u'] = plants_merged['Unit'].tolist()
sets['l'] = ['z1->z2','z2->z1']
sets['f'] = ['Coal','NG','Fuel','Nuclear','Bio','VRE','Elec','Other']
sets['p'] = ['Dummy']
sets['s'] = plants_sto['Unit'].tolist()
sets['t'] = ['CCGT','CL','D','GT','HU','HUSTO','IS','NU','TJ','WKK','WT','PV']
sets['tr'] = ['HU','IS','WT','PV']


###################################################################################################################
############################################   Parameters    ######################################################
###################################################################################################################

Nunits = len(plants_merged)
parameters = {}

# Availability Factor:
# The AvailabilityFactor parameter is used for the Variable Renewable generation (it is the fraction of the nominal
# power available at each hour). It is only relevant if data is available for the generation of individual VRE
# or CHP power plants. In this analysis, a value of 1 is imposed to all power plants.
# The data is provided on a daily basis, transforming into hours and building the gdx structure:

sets_in = ['u', 'h']
values = np.ones([len(sets[setx]) for setx in sets_in])
for i in range(Nunits):
        if plants_merged['Technology'][i] == 'WT':
            values[i,:]= AF_wind
        elif plants_merged['Technology'][i] == 'PV':
            values[i,:]= AF_sol
        elif plants_merged['Technology'][i] == 'HU':
            values[i,:] =  AF_water
        elif plants_merged['Technology'][i] == 'IS':
            values[i,:] =  AF_nondispatch[::4]
            
parameters['AvailabilityFactor'] = {'sets':sets_in,'val':values}

# Fixed cost parameter for each unit:
sets_in = ['u']
values = np.zeros([len(sets[setx]) for setx in sets_in])
parameters['CostFixed'] = {'sets':sets_in,'val':values}

# Shutdown cost parameter for each unit:
sets_in = ['u']
values = np.zeros([len(sets[setx]) for setx in sets_in])
parameters['CostShutDown'] = {'sets':sets_in,'val':values}

# Curtailment:
# For each node
# Set to 0 to impeed curtailment
# Set to 1 to allow. Max curtailement is the sum of renewable production at each time step
# if set higher than 1, multiplies renewable production
sets_in = ['n']
values = np.ones([len(sets[setx]) for setx in sets_in]) * curtailment
parameters['Curtailment'] = {'sets':sets_in,'val':values}

# Demand:
sets_in = ['mk', 'n', 'h']
values = np.ndarray([len(sets['mk']),len(sets['n']),len(sets['h'])])
values[0,0,:]=demand_z1.squeeze()
values[1,0,:]=reserve_2U_tot.squeeze()
values[2,0,:]=reserve_2D_tot.squeeze()
values[0,1,:]=demand_z2.squeeze()
values[1,1,:]=reserve_2U_tot.squeeze()
values[2,1,:]=reserve_2D_tot.squeeze()

parameters['Demand'] = {'sets':sets_in,'val':values}

# Plant Efficiency:
sets_in = ['u']
values = np.array(plants_merged['Efficiency'])
parameters['Efficiency'] = {'sets':sets_in,'val':values}

# Fuels:
sets_in = ['u', 'f']
values = np.zeros([len(sets[setx]) for setx in sets_in],dtype='bool')
parameters['Fuel'] = {'sets':sets_in,'val':values}
# not used at the modment in the gams file

# Biomass price
price_bio = 250                            # in EUR/T, source: http://www.michamps4b.be/evolution-prix-du-pellet-en-belgique.php
LHV = 5.28                                 # in MWh_th/T   (19 Gj/T)
price_bio = price_bio/LHV                  # in EUR/MWh_th
price_bio = max(0,price_bio - 60/0.4)      # Including green certificates into the fuel price (eta=0.4)

sets_in = ['u','h']
values = np.zeros([len(sets[setx]) for setx in sets_in])
for i in range(Nunits):
    if plants_merged['Fuel'][i] in ['NG','NG/BF','CG']:
        values[i,:] = price['gas']/plants_merged['Efficiency'][i]
    elif plants_merged['Fuel'][i] in ['CL','CP']:
        values[i,:] = price['coal']/plants_merged['Efficiency'][i]
    elif plants_merged['Fuel'][i] in ['LF','LV','GO']:
        values[i,:] = price['oil']/plants_merged['Efficiency'][i]
    elif plants_merged['Fuel'][i] in ['NU']:
        values[i,:] = 6 * np.ones(Nhours)
    elif plants_merged['Fuel'][i] in ['WI','WA','WR','SOL']:
        values[i,:] = np.zeros(Nhours)
    elif plants_merged['Fuel'][i] in ['WP','BF']:
        values[i,:] = price_bio * np.ones(Nhours)/plants_merged['Efficiency'][i]
    else:
        print 'No fuel price value has been found for fuel ' + plants_merged['Fuel'][i] + ' in unit ' +  plants_merged['Fuel'][i] + '. A null variable cost has been assigned'
parameters['CostVariable'] = {'sets':sets_in,'val':values}

# Fuel prices (not used in this case):
sets_in = ['n','f','h']
values = np.zeros([len(sets[setx]) for setx in sets_in])
parameters['FuelPrice'] = {'sets':sets_in,'val':values}

# Markup prices (not used in this case):
sets_in = ['u','h']
values = np.zeros([len(sets[setx]) for setx in sets_in])
parameters['Markup'] = {'sets':sets_in,'val':values}

# Start-up cost parameter:
sets_in = ['u']
values = np.zeros([len(sets[setx]) for setx in sets_in])
parameters['CostStartUp'] = {'sets':sets_in,'val':values}

# Maximum pollutant emissions:
# For each country and each emission type:
# In this case, we consider no limit => very high number
sets_in = ['n','p']
values = np.zeros([len(sets[setx]) for setx in sets_in])
parameters['EmissionMaximum'] = {'sets':sets_in,'val':values}

# Emission rate parameter (t/MWh):
# for each unit and each emission type:
# No emission considered for the time being
sets_in = ['u','p']
values = np.zeros([len(sets[setx]) for setx in sets_in])
parameters['EmissionRate'] = {'sets':sets_in,'val':values}

## Maximum line capacity:
# for each hour and each line:
sets_in = ['l','h']
values = 2000 * np.ones([len(sets[setx]) for setx in sets_in])
parameters['FlowMaximum'] = {'sets':sets_in,'val':values}


# Minimum line capacity (flows are always positive in Dispaset): 0
sets_in = ['l','h']
values = np.zeros([len(sets[setx]) for setx in sets_in])
parameters['FlowMinimum'] = {'sets':sets_in,'val':values}

# Nodes in lines - Incidence matrix:
# for each line, define the two boundary nodes:
# Assign -1 if 1 MW in the line removes power from node n
# Assign +1 if 1 MW in the line adds power to node n
sets_in = ['l','n']
values = np.array([ [-1 ,  1 ],
                    [ 1 , -1 ] ])
parameters['LineNode'] = {'sets':sets_in,'val':values}

# Location of each unit:
# For each unit, assign a 1 for the pair unit/node that corresponds
sets_in = ['u','n']
values = np.zeros([len(sets[setx]) for setx in sets_in])
values[:,0] = (plants_merged['Zone'] == 'z1').values
values[:,1] = (plants_merged['Zone'] == 'z2').values
parameters['Location'] = {'sets':sets_in,'val':values}

# Load Shedding capacity:
# For each node
# 331 MW available in the winter 2012-2013, in the form of interruptible contracts
sets_in = ['n']
values = np.ones([len(sets[setx]) for setx in sets_in]) * SheddingCapacity
parameters['LoadShedding'] = {'sets':sets_in,'val':values}

# OutageFactor parameter:
# In this analysis, we take as availability factor the outage data provided by Elia:
# The data is provided on a daily basis, transforming into hours and
sets_in = ['u','h']
values = 1-np.repeat(outages_merged,24,axis=1)
parameters['OutageFactor'] = {'sets':sets_in,'val':values}


# Price of pollutants (e.g. ETS system)
# Defining a cost of 5 EUR/Tco2
sets_in = ['p']
values = np.ones([len(sets[setx]) for setx in sets_in]) * CO2Price
parameters['PermitPrice'] = {'sets':sets_in,'val':values}

# Transmission price
# for each line and each hour.
# Assuming 0 => empty array
sets_in = ['l','h']
values = np.zeros([len(sets[setx]) for setx in sets_in])
parameters['PriceTransmission'] = {'sets':sets_in,'val':values}

sets_in = ['u']
values = np.array(plants_merged['PowerCapacity'])
parameters['PowerCapacity'] = {'sets':sets_in,'val':values}

# Minimum / must run capacity
sets_in = ['u']
values = np.array(plants_merged['PartLoadMin'])
parameters['PartLoadMin'] = {'sets':sets_in,'val':values}

# Ramping up/down
# for each unit, in MW/h
# PowerCapacity:
sets_in = ['u']
values = np.array(plants_merged['PowerCapacity'])*np.array(plants_merged['RampUpRate'])*60
parameters['RampUpMaximum'] = {'sets':sets_in,'val':values}

values = np.array(plants_merged['PowerCapacity'])*np.array(plants_merged['RampDownRate'])*60
parameters['RampDownMaximum'] = {'sets':sets_in,'val':values}

# Start up / Shut down
# for each unit, in MW/h
# In the data, the start_up is provided in hours to full load.
# start up ramping rate is given by the capacity divided by start-up time
# if start-up time is zero, it is assumed that full load can be reached in 15 minutes
sets_in = ['u']
values = np.array(plants_merged['PowerCapacity'])/np.maximum(np.array(plants_merged['StartUpTime']),0.25)
parameters['RampStartUpMaximum'] = {'sets':sets_in,'val':values}

# No data for shutdown times, taking the same time as start-up.
parameters['RampShutDownMaximum'] = {'sets':sets_in,'val':values}

# Participation to the reserve market
# Binary variable depending on the technology
# {'CCGT','CL','D','GT','HU','HUSTO','IS','NU','TJ','WKK','WT','PV'}
sets_in = ['t']
Ntech = len(sets['t'])
values = np.array([1,1,1,1,0,1,0,0,1,0,0,0],dtype='bool')
parameters['Reserve'] = {'sets':sets_in,'val':values}

# Discharge Efficiency parameter:
# for each pumped storage unit, setting the efficiency to sqrt(0.75):
sets_in = ['s']
values = np.ones([len(sets[setx]) for setx in sets_in]) * np.sqrt(StorageEfficiency)
parameters['StorageDischargeEfficiency'] = {'sets':sets_in,'val':values}

# Storage capacity:
# Assuming 4.5 hours at full load for all storage units:
sets_in = ['s']
values = plants_sto['PowerCapacity'].values*hours_sto 
parameters['StorageCapacity'] = {'sets':sets_in,'val':values}

# Storage inflow:
# for each hour and each storage unit
sets_in = ['s','h']
values = np.zeros([len(sets[setx]) for setx in sets_in])
parameters['StorageInflow'] = {'sets':sets_in,'val':values}

# Storage outflow:
# for each hour and each storage unit
sets_in = ['s','h']
values = np.zeros([len(sets[setx]) for setx in sets_in])
parameters['StorageOutflow'] = {'sets':sets_in,'val':values}

# Initial state (assuming half-filled):
sets_in = ['s']
values = plants_sto['PowerCapacity'].values*hours_sto/2
parameters['StorageInitial'] = {'sets':sets_in,'val':values}

# Minimum level:
sets_in = ['s']
values = np.zeros([len(sets[setx]) for setx in sets_in])
parameters['StorageMinimum'] = {'sets':sets_in,'val':values}

# Pumping Efficiency parameter:
# for each pumped storage unit, setting the efficiency to sqrt(0.75):
sets_in = ['s']
values = np.ones([len(sets[setx]) for setx in sets_in]) * np.sqrt(StorageEfficiency)
parameters['StorageChargingEfficiency'] = {'sets':sets_in,'val':values}

# Pumping Capacity parameter:
# Assuming the same power in pmping and in turbining mode:
sets_in = ['s']
values = plants_sto['PowerCapacity'].values
parameters['StorageChargingCapacity'] = {'sets':sets_in,'val':values}

# Technologies
# For each unit, parameter=1 if the input technology corresponds
sets_in = ['u','t']
values = np.zeros([len(sets[setx]) for setx in sets_in],dtype='bool')
for i in range(Nunits):
    idx_t = sets['t'].index(plants_merged['Technology'][i])    # Find the index of the plant type in 't':
    values[i,idx_t] = True            
parameters['Technology'] = {'sets':sets_in,'val':values}

# Minimum Time up/down
# In hours for each unit (values are set arbitrarily at the moment)
# assuming same value for up and down
sets_in = ['u']
value = []
values = np.zeros(Nunits)
for i in range(Nunits):
    if plants_merged['Technology'][i] in ['CCGT','CL']:
        values[i] = 5
    elif plants_merged['Technology'][i] in ['NU']:
        values[i] = 24
parameters['TimeDownMinimum'] = {'sets':sets_in,'val':values}
parameters['TimeUpMinimum'] = {'sets':sets_in,'val':values}

# Initial state:
# Number of hours the plant has been up or down at time 0
sets_in = ['u']
values =  np.ones(Nunits)*48
parameters['TimeDownInitial'] = {'sets':sets_in,'val':values}
parameters['TimeUpInitial'] = {'sets':sets_in,'val':values}

# Initial Power
# Three possibilities to define the initial power:
# - Use a very simple merit order and dispatch to define an initial state
#   that complies with the constraints
# - Use historical data
# - Set all values to zero => in this case, the UC model decides by itself

# In this case, we assume that all CCGT and NU plants are up initially, half way between pmin and pmax:
values = np.zeros(Nunits)
for i in range(Nunits):
    if plants_merged['Technology'][i] in ['CCGT','NU']:
        values[i] = (plants_merged['PartLoadMin'][i]+1)/2 * plants_merged['PowerCapacity'][i] * outages_merged[i][0]
parameters['PowerInitial'] = {'sets':['u'],'val':values}


# Config variables:
sets['x_config'] = ['FirstDay','LastDay','DayStart','DayStop','RollingHorizon Length','RollingHorizon LookAhead']
sets['y_config'] = ['year','month','day']
dd = pd.to_datetime(dates_h_ymd)
dd_begin = dd[0]+pd.Timedelta(days=cropping_beginning)
dd_end = dd[-1] - pd.Timedelta(days=cropping_end)
values = np.array([
    [dd.year[0],    dd.month[0],    dd.day[0]               ],
    [dd.year[-1],   dd.month[-1],   dd.day[-1]              ],
    [dd_begin.year, dd_begin.month, dd_begin.day            ],
    [dd_end.year,   dd_end.month,   dd_end.day              ],
    [0,             0,              RollingHorizon_length   ],
    [0,             0,              RollingHorizon_lookahead]
])
parameters['Config'] = {'sets':['x_config','y_config'],'val':values}

list_vars = []
gdx_out = "../GAMS-files/Inputs.gdx"
if write_gdx:
    write_variables(gams_dir,gdx_out,[sets,parameters],format='2.1.1')

###################################################################################################################
#####################################   Simulation Environment     ################################################
###################################################################################################################

# if the sim variable was not defined:
if 'sim' not in locals():
    sys.exit('Please provide a path where to store the DispaSET inputs (in the "sim" variable)')

if not os.path.exists(sim):
    os.mkdir(sim)
shutil.copyfile('../GAMS-files/UCM_h.gms',sim + '/UCM_h.gms')
gmsfile = open(os.path.join(sim,'UCM.gpr'),'w')
gmsfile.write('[PROJECT] \n \n[RP:UCM_H] \n1= \n[OPENWINDOW_1] \nFILE0=UCM_h.gms \nFILE1=UCM_h.gms \nMAXIM=1 \nTOP=50 \nLEFT=50 \nHEIGHT=400 \nWIDTH=400')
gmsfile.close()
shutil.copyfile('../GAMS-files/writeresults.gms',sim + '/writeresults.gms')
#if not os.path.exists(sim + '/python-files'):
#    shutil.copytree('../python-files',sim + '/python-files')
if write_gdx:
    shutil.copy(gdx_out,sim + '/')
#shutil.copy(os.path.realpath(__file__),sim + '/DispaSET.py')
# Copy bat file to generate gdx file directly from excel:
shutil.copy('../GAMS-files/makeGDX.bat',os.path.join(sim,'makeGDX.bat'))

if write_excel:
    write_toexcel(sim,[sets,parameters],format='2.1.1')
    
if write_pickle:
    import cPickle
    with open(sim + '/Inputs.p', 'wb') as pfile:
        cPickle.dump([sets, parameters], pfile, protocol=cPickle.HIGHEST_PROTOCOL)

###################################################################################################################
#####################################   Plotting load and VRE      ################################################
###################################################################################################################

# Plotting the 15-min data for a visual check:
N = len(demand_z2)
plt.plot(demand_z1,label='Load, zone 1')
plt.plot(demand_z2,label='Load, zone 2')

x_ticks = np.linspace(0,N-1,20,dtype='int32')
plt.xticks(x_ticks, [dates_h_ymd[x] for x in x_ticks/4], rotation='vertical')
plt.ylabel('Power (MW)')
fig = plt.gcf()
fig.subplots_adjust(bottom=0.2)

plt.legend()
plt.show()
a = 1
