import os
import geopandas as gpd
import numpy as np
import cv2
import base64
from shapely.geometry import LineString, MultiLineString
from shapely.ops import unary_union


class Bounds:
    def __init__(self, minx, miny, maxx, maxy):
        self.minx = minx
        self.miny = miny
        self.maxx = maxx
        self.maxy = maxy

class Rete():
    def __init__(self, shapeFile = None, distance_threshold=0.000001, angle_threshold=10, scale=1000):
        self.input_shapefile = shapeFile
        self.distance_threshold = distance_threshold
        self.angle_threshold = angle_threshold
        self.scale = scale

        self.streets_geometry = None
        self.grouped_lines = None
        self.bounds = Bounds(float('-inf'), float('-inf'), float('inf'), float('inf'))
        self.image = None
        self.blob_url = None
        self.geojson = None
        self.result = {"errors":""}
        self.status = False


    def color_streets(self):
        # Step 1: Open Shapefile
        gdf = None
        try:
            gdf = gpd.read_file(self.input_shapefile, ignore_missing_files=True)
            #self.geojson = self.input_shapefile + '.geojson'
            #gdf.to_file(self.input_shapefile + '.geojson', driver='GeoJSON')
        except Exception as ex:
            self.result["errors"] += f"\n{str(ex)}"
            self.result["success"] = False
            return self.status

        # Step 2: Union all objects to LineString або MultiLineString
        self.streets_geometry = gdf.unary_union

        # Step 3: group lines
        self.grouped_lines = self.group_lines()

        # Step 4: group lines to image
        self.image = self.lines_to_image(self.grouped_lines, scale=5000)
        self.save_image_with_format_0(self.image, self.input_shapefile + '.png')
        # self.save_image_with_format(self.image, os.path.basename(self.input_shapefile) + '.png')
        self.image_to_base64()
        if self.image is None:
            ...
        else:
            self.blob_url = "data:image/png;base64," + self.image
            self.status = True
        self.to_geojson()

        return self.status

    def group_lines(self):
        lines = []
        # Розділити MultiLineString на окремі лінії
        if isinstance(self.streets_geometry, MultiLineString):
            lines.extend(list(self.streets_geometry.geoms))
        elif isinstance(self.streets_geometry, LineString):
            lines.append(self.streets_geometry)

        # Групувати лінії за відстанню та кутами стикання
        grouped_lines = []
        while lines:
            current_line = lines.pop(0)
            group = [current_line]
            i = 0
            while i < len(lines):
                line = lines[i]
                if current_line.distance(line) < self.distance_threshold\
                        and not self.are_perpendicular(current_line, line):
                        # and self.get_angle_difference(current_line, line) < self.angle_threshold\
                    group.append(line)
                    lines.pop(i)
                else:
                    i += 1
            grouped_lines.append(group)

        return grouped_lines

    def are_perpendicular(self, line1, line2):
        # Обчислити кут стикання між двома лініями
        # angle_radians = np.abs(LineString(line1).difference(LineString(line2)).angle)
        dx1, dy1 = line1.coords[-1][0] - line1.coords[0][0], line1.coords[-1][1] - line1.coords[0][1]
        dx2, dy2 = line2.coords[-1][0] - line2.coords[0][0], line2.coords[-1][1] - line2.coords[0][1]
        angle_radians = np.arccos((dx1 * dx2 + dy1 * dy2) / (np.hypot(dx1, dy1) * np.hypot(dx2, dy2)))
        angle_degrees = np.degrees(angle_radians)
        return angle_degrees < self.angle_threshold

    def get_angle_difference(self, line1, line2):
        # Обчислити кут стикання між двома лініями
        dx1, dy1 = line1.coords[-1][0] - line1.coords[0][0], line1.coords[-1][1] - line1.coords[0][1]
        dx2, dy2 = line2.coords[-1][0] - line2.coords[0][0], line2.coords[-1][1] - line2.coords[0][1]
        angle_radians = np.arccos((dx1 * dx2 + dy1 * dy2) / (np.hypot(dx1, dy1) * np.hypot(dx2, dy2)))
        angle_degrees = np.degrees(angle_radians)
        return angle_degrees

    def get_bounds(self, grouped_lines):
        minx, miny, maxx, maxy = float('inf'), float('inf'), float('-inf'), float('-inf')
        for group in grouped_lines:
            for line in group:
                x, y = zip(*line.coords)
                minx, miny = min(min(x), minx), min(min(y), miny)
                maxx, maxy = max(max(x), maxx), max(max(y), maxy)
        self.bounds = Bounds(minx, miny, maxx, maxy)
        return self.bounds

    def lines_to_image(self, grouped_lines, scale = 1000):
        bounds = self.get_bounds(self.grouped_lines)

        # Обчислити розміри зображення на основі географічних координат
        scale_x = scale / (bounds.maxx - bounds.minx)
        scale_y = scale / (bounds.maxy - bounds.miny)
        width = int(np.ceil((bounds.maxx - bounds.minx) * scale_x))
        height = int(np.ceil((bounds.maxy - bounds.miny) * scale_y))

        # Створимо пусте зображення
        image = np.zeros((height, width, 3), dtype=np.uint8) * 255

        # Позначимо кожну групу ліній унікальним кольором
        for idx, group in enumerate(grouped_lines):
            color = tuple(int(255 * x) for x in np.random.rand(3))  # Випадковий колір для кожної вулиці
            for line in group:
                coords = np.array(line.coords)
                coords[:, 0] = (coords[:, 0] - bounds.minx) * scale_x
                coords[:, 1] = (coords[:, 1] - bounds.miny) * scale_y
                coords = coords.astype(np.int32)
                cv2.polylines(image, [coords], isClosed=False, color=color, thickness=2)

        return image

    def save_image_with_format_0(self, image, output_image_path):
        # Get image size
        height, width, _ = image.shape

        # Create white canvas with OpenCV
        white_image = np.ones((height, width, 3), dtype=np.uint8) * 255

        # Копіювати канали зображення у біле зображення
        white_image[:, :, 0] = image[:, :, 0]
        white_image[:, :, 1] = image[:, :, 1]
        white_image[:, :, 2] = image[:, :, 2]

        # Додати темно-сірі осі з OpenCV
        cv2.line(white_image, (0, height - 1), (width - 1, height - 1), (100, 100, 100), 2)
        cv2.line(white_image, (0, 0), (0, height - 1), (100, 100, 100), 2)

        # Додати округлені координати текстом з OpenCV
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.5
        font_thickness = 1
        font_color = (100, 100, 100)

        for x in range(0, width, 100):
            x_text = round(x * 0.01, 2)
            cv2.putText(white_image, str(x_text), (x, height - 10), font, font_scale, font_color, font_thickness)

        for y in range(0, height, 100):
            y_text = round(y * 0.01, 2)
            cv2.putText(white_image, str(y_text), (5, y), font, font_scale, font_color, font_thickness)

        # Save image
        cv2.imwrite(output_image_path, white_image)

    def save_image_with_format(self, image, output_image_path):
        # Get image size
        height, width, _ = image.shape

        # Create white canvas with OpenCV
        white_image = np.ones((height, width, 3), dtype=np.uint8) * 255

        white_image[:, :, 0] = image[:, :, 0]
        white_image[:, :, 1] = image[:, :, 1]
        white_image[:, :, 2] = image[:, :, 2]

        # Add coordinates as text with OpenCV
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.5
        font_thickness = 1
        font_color = (100, 100, 100)

        # Step 1: Calculate scales by axis
        bounds = self.get_bounds(self.grouped_lines)
        scale_x = (bounds.maxx - bounds.minx) / width
        scale_y = (bounds.maxy - bounds.miny) / height

        # Step 2: Add coordinate to scale X
        for x in np.arange(0, width, int(0.005 / scale_x)):
            x_geo = round(x * scale_x + bounds.minx, 2)
            cv2.putText(white_image, str(x_geo), (x, height - 10), font, font_scale, font_color, font_thickness)

        # Step 3: Add coordinate to scale Y
        for y in np.arange(0, height, int(0.005 / scale_y)):
            y_geo = round(y * scale_y + bounds.miny, 2)
            cv2.putText(white_image, str(y_geo), (5, y), font, font_scale, font_color, font_thickness)

        # Step 4: Add axes with OpenCV
        cv2.line(white_image, (0, height - 1), (width - 1, height - 1), (100, 100, 100), 2)
        cv2.line(white_image, (0, 0), (0, height - 1), (100, 100, 100), 2)

        # Step 5: Add colored lines
        white_image = self.add_colored_lines(white_image, self.grouped_lines)

        # Save Image
        cv2.imwrite(output_image_path, white_image)

    def add_colored_lines(self, image, grouped_lines):
        for idx, group in enumerate(grouped_lines):
            color = tuple(np.random.randint(0, 255, 3).tolist())  # Random color for grouped line
            for line in group:
                coords = np.array(line.coords)
                coords = coords.astype(np.int32)
                cv2.polylines(image, [coords], isClosed=False, color=color, thickness=2)
        return image

    def image_to_base64(self):
        _, buffer = cv2.imencode('.png', self.image)
        self.image = base64.b64encode(buffer).decode('utf-8')
        return self.image

    def rgb_to_hex(self, rgb_color):
        # Ensure the RGB values are integers (OpenCV sometimes returns float values)
        r, g, b = map(int, rgb_color)
        # Convert RGB to hex format
        hex_color = "#{:02x}{:02x}{:02x}".format(r, g, b)
        return hex_color

    def to_geojson(self):
        geometries = []
        colors = []
        group_numbers = []

        for group_number, group in enumerate(self.grouped_lines, 1):
            # merge geometry in group into one geometry
            merged_geometry = None
            for line_or_multiline in group:
                if merged_geometry is None:
                    merged_geometry = line_or_multiline
                elif isinstance(line_or_multiline, LineString):
                    merged_geometry = merged_geometry.union(line_or_multiline)
                elif isinstance(line_or_multiline, MultiLineString):
                    merged_geometry = merged_geometry.union(line_or_multiline)

            # geometry, color, group_id
            geometries.append(merged_geometry)
            color = self.rgb_to_hex(tuple(np.random.randint(0, 255, 3).tolist()))
            colors.append(color)  # random color
            group_numbers.append(group_number)

        # Create GeoDataFrame
        gdf = gpd.GeoDataFrame({'geometry': geometries, 'color': colors, 'group_number': group_numbers})

        # path to new  GeoJSON
        output_geojson_path = self.input_shapefile + "_out.geojson"


        # Save GeoDataFrame as GeoJSON
        gdf.to_file(output_geojson_path, driver='GeoJSON')
        self.geojson = gdf.__geo_interface__



if __name__ == '__main__':
    shp_file = r"/Users/viktor/LinkedIn/jun-python-gis-test-task-master/sample/roads.shp"
    shp_obj = Rete(shapeFile=shp_file,distance_threshold=0.000001, angle_threshold=10)
    # shp_obj.color_streets()

    image = shp_obj.color_streets()
    # shp_obj.save_image_with_format_0()
    pass