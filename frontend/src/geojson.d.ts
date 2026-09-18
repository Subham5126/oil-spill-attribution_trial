declare namespace GeoJSON {
  type Geometry =
    | Point
    | MultiPoint
    | LineString
    | MultiLineString
    | Polygon
    | MultiPolygon
    | GeometryCollection;
  type Position = number[];
  interface Point { type: "Point"; coordinates: Position }
  interface MultiPoint { type: "MultiPoint"; coordinates: Position[] }
  interface LineString { type: "LineString"; coordinates: Position[] }
  interface MultiLineString { type: "MultiLineString"; coordinates: Position[][] }
  interface Polygon { type: "Polygon"; coordinates: Position[][] }
  interface MultiPolygon { type: "MultiPolygon"; coordinates: Position[][][] }
  interface GeometryCollection { type: "GeometryCollection"; geometries: Geometry[] }
  interface Feature<G extends Geometry | null = Geometry, P = Record<string, unknown>> {
    type: "Feature";
    geometry: G;
    properties: P;
  }
  interface FeatureCollection<G extends Geometry | null = Geometry> {
    type: "FeatureCollection";
    features: Feature<G>[];
  }
}

