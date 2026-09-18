declare module "@deck.gl/core" {
  export class Layer<P = any> {
    constructor(props?: P);
  }
}

declare module "@deck.gl/layers" {
  import { Layer } from "@deck.gl/core";
  export class PathLayer<D = any, P = any> extends Layer<P> {
    constructor(props?: any);
  }
  export class PolygonLayer<D = any, P = any> extends Layer<P> {
    constructor(props?: any);
  }
  export class ScatterplotLayer<D = any, P = any> extends Layer<P> {
    constructor(props?: any);
  }
}

declare module "@deck.gl/geo-layers" {
  import { Layer } from "@deck.gl/core";
  export class TripsLayer<D = any, P = any> extends Layer<P> {
    constructor(props?: any);
  }
}

declare module "@deck.gl/mapbox" {
  export class MapboxOverlay {
    constructor(props?: any);
    setProps(props: any): void;
    finalize(): void;
  }
}
