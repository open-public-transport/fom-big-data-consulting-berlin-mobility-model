import csv
from os import path

import geopy.distance
import networkx as nx
import numpy as np
import osmnx as ox
from geojson import FeatureCollection
from shapely.geometry import MultiPoint
from tqdm import tqdm


def load_graphml_from_file(file_path, place_name, network_type=None, custom_filter=None):
    if not path.exists(file_path):
        print("Download " + file_path)
        graph = load_graphml(place_name=place_name,
                             network_type=network_type,
                             custom_filter=custom_filter)
        ox.save_graphml(graph, file_path)
        return graph
    else:
        print("Load " + file_path)
        return ox.io.load_graphml(file_path)


def load_graphml(place_name, network_type=None, custom_filter=None):
    return ox.graph.graph_from_place(query=place_name,
                                     simplify=True,
                                     retain_all=False,
                                     buffer_dist=2500,
                                     network_type=network_type,
                                     custom_filter=custom_filter)


def get_means_of_transport_graph(transport, enhance_with_speed=False):
    if transport == "all":
        return nx.algorithms.operators.all.compose_all([get_means_of_transport_graph(transport="bus", enhance_with_speed=True),
                                                        get_means_of_transport_graph(transport="subway", enhance_with_speed=True),
                                                        get_means_of_transport_graph(transport="tram", enhance_with_speed=True),
                                                        get_means_of_transport_graph(transport="light_rail", enhance_with_speed=True)])
    else:
        g_transport = None

        if transport == "walk":
            g_transport = load_graphml_from_file(file_path='tmp/walk.graphml',
                                                 place_name=PLACE_NAME,
                                                 network_type='walk')
        elif transport == "bike":
            g_transport = load_graphml_from_file(file_path="tmp/" + transport + ".graphml",
                                                 place_name=PLACE_NAME,
                                                 network_type='bike')
        elif transport == "bus":
            g_transport = load_graphml_from_file(file_path="tmp/" + transport + ".graphml",
                                                 place_name=PLACE_NAME,
                                                 custom_filter='["highway"~"secondary|tertiary|residential|bus_stop"]')
        elif transport == "light_rail":
            g_transport = load_graphml_from_file(file_path="tmp/" + transport + ".graphml",
                                                 place_name=PLACE_NAME,
                                                 custom_filter='["railway"~"light_rail|station"]["railway"!="light_rail_entrance"]["railway"!="service_station"]["station"!="subway"]')
        elif transport == "subway":
            g_transport = load_graphml_from_file(file_path="tmp/" + transport + ".graphml",
                                                 place_name=PLACE_NAME,
                                                 custom_filter='["railway"~"subway|station"]["railway"!="subway_entrance"]["railway"!="service_station"]["station"!="light_rail"]["service"!="yard"]')
        elif transport == "tram":
            g_transport = load_graphml_from_file(file_path="tmp/" + transport + ".graphml",
                                                 place_name=PLACE_NAME,
                                                 custom_filter='["railway"~"tram|tram_stop"]["railway"!="tram_crossing"]["train"!="yes"]["station"!="subway"]["station"!="light_rail"]')

        if enhance_with_speed:
            return enhance_graph_with_speed(g=g_transport, transport=transport)
        else:
            return g_transport


def enhance_graph_with_speed(g, time_attribute='time', transport=None):
    for _, _, _, data in g.edges(data=True, keys=True):

        speed = None

        if (transport == 'walk'):
            speed = 6.0
        elif (transport == 'bus'):
            speed = 19.5
        elif (transport == 'bike'):
            speed = 16.0
        elif (transport == 'subway'):
            speed = 31.0
        elif (transport == 'tram'):
            speed = 19.0
        elif (transport == 'light_rail'):
            speed = 38.0

        if speed is not None:
            data[time_attribute] = data['length'] / (float(speed) * 1000 / 60)

    return g


def compose_graphs(file_path, g_a, g_b, connect_a_to_b=False):
    """
    Composes two graphs into one

    Parameters
    ----------
    :param g_a : MultiDiGraph First graph.
    :param g_b : MultiDiGraph Second graph.
    :param connect_a_to_b : bool If true, each node of first graph will be connected to the closest node of the second graph via an edge
    :return composed graph
    """
    g = nx.algorithms.operators.all.compose_all([g_a, g_b])

    if connect_a_to_b:
        a_nodes, a_edges = ox.graph_to_gdfs(g_a)
        b_nodes, b_edges = ox.graph_to_gdfs(g_b)

        # Iterate over all nodes of first graph
        for key, a_node_id in tqdm(iterable=a_nodes["osmid"].items(),
                                   desc="Compose graphs",
                                   total=len(a_nodes),
                                   unit="point"):
            # Get coordinates of node
            a_nodes_point = g_a.nodes[a_node_id]

            # Get node in second graph that is closest to node in first graph
            b_node_id, distance = ox.get_nearest_node(g_b, (a_nodes_point["y"], a_nodes_point["x"]), return_dist=True)

            # Add edges in both directions
            g.add_edge(a_node_id, b_node_id,
                       osmid=0,
                       name="Way from station",
                       highway="tertiary",
                       maxspeed="50",
                       oneway=False,
                       length=0,
                       time=0)
            g.add_edge(b_node_id, a_node_id,
                       osmid=0,
                       name="Way to station",
                       highway="tertiary",
                       maxspeed="50",
                       oneway=False,
                       length=0,
                       time=0)

    ox.save_graphml(g, file_path)
    return g


def load_sample_points(file_path):
    with open(file_path, newline="") as csvfile:
        reader = csv.reader(csvfile, delimiter=",")

        sample_points = []

        for lon, lat in reader:
            sample_points.append({"lon": lon, "lat": lat})

    return sample_points


def get_points_with_spatial_distance(g, points, travel_time_minutes):
    points_with_spatial_distance = []
    failed_points = []
    mean_spatial_distances = []
    median_spatial_distances = []
    min_spatial_distances = []
    max_spatial_distances = []

    for point_index in tqdm(iterable=range(len(points)),
                            total=len(points),
                            desc="Evaluate points",
                            unit="point", ):
        point = points[point_index]
        start_point = (float(point["lat"]), float(point["lon"]))

        mean_spatial_distance, \
        median_spatial_distance, \
        min_spatial_distance, \
        max_spatial_distance = get_spatial_distance(g=g,
                                                    start_point=start_point,
                                                    travel_time_minutes=travel_time_minutes)

        point_with_spatial_distance = {
            "lon": point["lon"],
            "lat": point["lat"],
            "mean_spatial_distance_" + str(travel_time_minutes) + "min": mean_spatial_distance,
            "median_spatial_distance_" + str(travel_time_minutes) + "min": median_spatial_distance,
            "min_spatial_distance_" + str(travel_time_minutes) + "min": min_spatial_distance,
            "max_spatial_distance_" + str(travel_time_minutes) + "min": max_spatial_distance
        }

        if mean_spatial_distance > 0:
            mean_spatial_distances.append(mean_spatial_distance)
            median_spatial_distances.append(median_spatial_distance)
            min_spatial_distances.append(min_spatial_distance)
            max_spatial_distances.append(max_spatial_distance)
            points_with_spatial_distance.append(point_with_spatial_distance)
        else:
            failed_points.append(point_with_spatial_distance)

    return points_with_spatial_distance, \
           failed_points, \
           mean_spatial_distances, \
           median_spatial_distances, \
           min_spatial_distances, \
           max_spatial_distances


def get_spatial_distance(g, start_point, travel_time_minutes, distance_attribute='time'):
    walking_distance_meters = 0

    try:
        nodes, edges, walking_distance_meters = get_possible_routes(g,
                                                                    start_point,
                                                                    travel_time_minutes,
                                                                    distance_attribute)

        longitudes, latitudes = get_convex_hull(nodes)
        transport_distances_meters = get_distances(start_point, latitudes, longitudes)

        return np.mean(transport_distances_meters) + walking_distance_meters, \
               np.median(transport_distances_meters) + walking_distance_meters, \
               np.min(transport_distances_meters) + walking_distance_meters, \
               np.max(transport_distances_meters) + walking_distance_meters
    except:
        return walking_distance_meters, walking_distance_meters, walking_distance_meters, walking_distance_meters


def get_possible_routes(g, start_point, travel_time_minutes, distance_attribute, calculate_walking_distance=False):
    center_node, distance_to_station_meters = ox.get_nearest_node(g, start_point, return_dist=True)

    if calculate_walking_distance:
        walking_speed_meters_per_minute = 100
        walking_time_minutes = distance_to_station_meters / walking_speed_meters_per_minute

        walking_time_minutes_max = walking_time_minutes if walking_time_minutes < travel_time_minutes else travel_time_minutes
        walking_distance_meters = walking_time_minutes_max * walking_speed_meters_per_minute

        radius = travel_time_minutes - walking_time_minutes
    else:
        walking_distance_meters = 0
        radius = travel_time_minutes

    if radius > 0:
        subgraph = nx.ego_graph(g, center_node, radius=radius, distance=distance_attribute)

        # write_nodes_to_geojson(subgraph, "debug-" + str(start_point[0]) + "-" + str(start_point[1]) + ".geojson")

        nodes, edges = ox.graph_to_gdfs(subgraph)
        return nodes, edges, walking_distance_meters
    else:
        return [], [], walking_distance_meters


def get_convex_hull(nodes):
    return MultiPoint(nodes.reset_index()["geometry"]).convex_hull.exterior.coords.xy


def get_distances(start_point, latitudes, longitudes):
    return [geopy.distance.geodesic(point, start_point).meters for point in zip(latitudes, longitudes)]


def write_coords_to_geojson(file_path, coords, travel_time_min):
    features = []
    for coord in coords:
        feature = {}
        feature["geometry"] = {"type": "Point", "coordinates": [coord["lon"], coord["lat"]]}
        feature["type"] = "Feature"
        feature["properties"] = {
            "mean_spatial_distance_" + str(travel_time_min) + "min": coord["mean_spatial_distance_" + str(travel_time_min) + "min"],
            "median_spatial_distance_" + str(travel_time_min) + "min": coord["median_spatial_distance_" + str(travel_time_min) + "min"],
            "min_spatial_distance_" + str(travel_time_min) + "min": coord["min_spatial_distance_" + str(travel_time_min) + "min"],
            "max_spatial_distance_" + str(travel_time_min) + "min": coord["max_spatial_distance_" + str(travel_time_min) + "min"],
        }
        features.append(feature)

    collection = FeatureCollection(features)

    with open(file_path, "w") as f:
        f.write("%s" % collection)


def write_spatial_distances_to_file(file_path,
                                    mean_spatial_distances,
                                    median_spatial_distances,
                                    min_spatial_distances,
                                    max_spatial_distances):
    with open(file_path, "w") as f:
        f.write("  mean distance min " + str(min(mean_spatial_distances)) + " / max " + str(max(mean_spatial_distances)) + "\n")
        f.write("median distance min " + str(min(median_spatial_distances)) + " / max " + str(max(median_spatial_distances)) + "\n")
        f.write("   min distance min " + str(min(min_spatial_distances)) + " / max " + str(max(min_spatial_distances)) + "\n")
        f.write("   max distance min " + str(min(max_spatial_distances)) + " / max " + str(max(max_spatial_distances)) + "\n")


def plot_graph(g):
    ox.plot_graph(g)


#
# Main
#

PLACE_NAME = "Berlin, Germany"
TRAVEL_TIMES_MINUTES = [15]
MEANS_OF_TRANSPORT = ["all", "bike", "bus", "light_rail", "subway", "tram"]
OVERRIDE_RESULTS = False

# Load walk graph
g_walk = get_means_of_transport_graph(transport="walk", enhance_with_speed=True)

# Load sample points
sample_points = load_sample_points(file_path="../results/sample-points.csv")

# Iterate over means of transport
for transport in MEANS_OF_TRANSPORT:

    # Get graph for means of transport
    g_transport = get_means_of_transport_graph(transport=transport, enhance_with_speed=True)

    # Compose transport graph and walk graph
    g = compose_graphs("tmp/" + transport + "+walk.graphml", g_transport, g_walk, connect_a_to_b=True)

    # Iterate over travel times
    for travel_time_minutes in TRAVEL_TIMES_MINUTES:

        result_file_name_base = "../results/isochrones-" + transport + "-" + str(travel_time_minutes)
        result_file_name_base_failed = "../results/failed/isochrones-" + transport + "-" + str(travel_time_minutes)
        result_file_name_base_distances = "../results/distances/isochrones-" + transport + "-" + str(travel_time_minutes)

        if not path.exists(result_file_name_base + ".geojson") or OVERRIDE_RESULTS:
            print(">>> Analyze " + transport + " in " + str(travel_time_minutes) + " minutes")

            # Generate points
            points_with_spatial_distance, \
            failed_points, \
            mean_spatial_distances, \
            median_spatial_distances, \
            min_spatial_distances, \
            max_spatial_distances = get_points_with_spatial_distance(g=g,
                                                                     points=sample_points,
                                                                     travel_time_minutes=travel_time_minutes)

            # Write results to file
            write_coords_to_geojson(file_path=result_file_name_base + ".geojson",
                                    coords=points_with_spatial_distance,
                                    travel_time_min=travel_time_minutes)
            write_coords_to_geojson(file_path=result_file_name_base_failed + "-failed.geojson",
                                    coords=failed_points,
                                    travel_time_min=travel_time_minutes)
            write_spatial_distances_to_file(file_path=result_file_name_base_distances + "-distances.txt",
                                            mean_spatial_distances=mean_spatial_distances,
                                            median_spatial_distances=median_spatial_distances,
                                            min_spatial_distances=min_spatial_distances,
                                            max_spatial_distances=max_spatial_distances)
        else:
            print(">>> Exists " + transport + " in " + str(travel_time_minutes) + " minutes")

print("Complete!")
