import pyproj
import pooch
import numpy as np
import xarray as xr
import verde as vd
import boule as bl
import harmonica as hm
import matplotlib.pyplot as plt


print("Harmonica version: {}".format(hm.__version__))

# Fetch gravity data and DEM
data = hm.datasets.fetch_south_africa_gravity()
url = "https://github.com/fatiando/transform21/raw/main/data/bushveld_topography.nc"
fname = pooch.retrieve(url, known_hash=None, fname="bushveld_topography.nc")
topography = xr.load_dataset(fname).bedrock

# Project the dataset coordinates
projection = pyproj.Proj(proj="merc", lat_ts=data.latitude.mean())
easting, northing = projection(data.longitude.values, data.latitude.values)
data = data.assign(easting=easting)
data = data.assign(northing=northing)

# Cut the datasets to a very small region to run the script faster
region_deg = (28, 29, -26, -25)
inside = vd.inside((data.longitude, data.latitude), region_deg)
data = data[inside]
topography = topography.sel(
    longitude=slice(*region_deg[:2]), latitude=slice(*region_deg[2:])
)

# Compute gravity disturbance
ell = bl.WGS84
gravity_disturbance = data.gravity.values - ell.normal_gravity(
    data.latitude.values, data.elevation.values
)
data = data.assign(gravity_disturbance=gravity_disturbance)

# Project data and topography
projection = pyproj.Proj(proj="merc", lat_ts=data.latitude.mean())
easting, northing = projection(data.longitude.values, data.latitude.values)
data = data.assign(easting=easting)
data = data.assign(northing=northing)
topo_plain = vd.project_grid(topography, projection=projection)

# Compute Bouguer disturbance
topo_prisms = hm.prism_layer(
    (topo_plain.easting.values, topo_plain.northing.values),
    surface=topo_plain.values,
    reference=0,
    properties={"density": 2670 * np.ones_like(topo_plain.values)},
)
coordinates = (data.easting.values, data.northing.values, data.elevation.values)
result = topo_prisms.prism_layer.gravity(coordinates, field="g_z")
bouguer_disturbance = data.gravity_disturbance - result
data = data.assign(bouguer_disturbance=bouguer_disturbance)

# Compute residuals
trend = vd.Trend(degree=2)
trend.fit(coordinates, data.bouguer_disturbance)
residuals = data.bouguer_disturbance - trend.predict(coordinates)
data = data.assign(bouguer_residuals=residuals)

# Grid
eql = hm.EQLHarmonic(damping=1e2, relative_depth=5e3)
eql.fit(coordinates, data.bouguer_residuals.values)
grid = eql.grid(
    upward=2200,
    region=region_deg,
    spacing=0.01,
    data_names=["bouguer_residuals"],
    dims=("latitude", "longitude"),
    projection=projection,
)

# Plot
grid.bouguer_residuals.plot()
plt.gca().set_aspect("equal")
