from shapely.geometry import Polygon,Point

parcel=Polygon([(0,0),(10,0),(10,10),(0,10),(0,0)])
query=Polygon([(5,5),(15,5),(15,15),(5,15),(5,5)])
intersection=parcel.intersection(query)
assert round(intersection.area,6)==25
assert round(intersection.area/query.area,6)==0.25
assert parcel.covers(Point(5,5))
assert not parcel.covers(Point(20,20))
# Blueprint invariant used by v15: spatial relations are explicit and reproducible,
# not inferred by the language model.
print('v15 spatial math contract OK')
