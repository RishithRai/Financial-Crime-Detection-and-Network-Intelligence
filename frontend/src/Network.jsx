import React, { useEffect, useMemo, useRef } from "react";
import cytoscape from "cytoscape";
import { networkElements } from "./model";
export default function Network({ report, selection, onSelect, onReset }) {
  const container = useRef(),
    cy = useRef();
  const graph = useMemo(() => networkElements(report), [report]);
  const callback = useRef(onSelect);
  callback.current = onSelect;
  useEffect(() => {
    const instance = cytoscape({
      container: container.current,
      elements: graph.elements,
      minZoom: 0.1,
      maxZoom: 4,
      wheelSensitivity: 0.2,
      layout: {
        name: "concentric",
        animate: false,
        concentric: (node) => (node.data("root") ? 2 : 1),
        levelWidth: () => 1,
        minNodeSpacing: 65,
        nodeDimensionsIncludeLabels: true,
        avoidOverlap: true,
        padding: 50,
      },
      style: [
        {
          selector: "node",
          style: {
            label: "data(label)",
            "background-color": "#648de8",
            width: 36,
            height: 36,
            "font-size": 11,
            color: "#dce7fb",
            "text-valign": "bottom",
            "text-wrap": "wrap",
            "text-margin-y": 9,
            "text-background-color": "#101d30",
            "text-background-opacity": 0.9,
            "text-background-padding": 3,
          },
        },
        {
          selector: "node[?root]",
          style: {
            "background-color": "#edbb69",
            width: 48,
            height: 48,
            "border-width": 3,
            "border-color": "#fff0d2",
          },
        },
        {
          selector: "node[?focalOnly]",
          style: {
            "border-style": "dashed",
            "border-width": 3,
            "border-color": "#edbb69",
          },
        },
        {
          selector: "edge",
          style: {
            width: 2,
            "line-color": "#526a8f",
            "target-arrow-color": "#7892b8",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            label: "data(displayLabel)",
            "font-size": 10,
            color: "#b0c1dd",
            "text-background-color": "#101d30",
            "text-background-opacity": 1,
            "text-background-padding": 3,
            "text-rotation": "autorotate",
          },
        },
        {
          selector: "edge[?focal]",
          style: {
            "line-color": "#edbb69",
            "target-arrow-color": "#edbb69",
            "line-style": "dashed",
            width: 3,
            color: "#edbb69",
          },
        },
        {
          selector: ".evidence",
          style: {
            "line-color": "#69e2c0",
            "target-arrow-color": "#69e2c0",
            "background-color": "#69e2c0",
            width: 5,
            "z-index": 20,
          },
        },
        {
          selector: "node.evidence",
          style: {
            width: 44,
            height: 44,
            "border-color": "#69e2c0",
            "border-width": 3,
          },
        },
        {
          selector: "node[?root].evidence",
          style: { "border-color": "#edbb69", "border-width": 4 },
        },
        { selector: ".muted", style: { opacity: 0.3 } },
        {
          selector: "node.focused",
          style: { "border-color": "#73d8ff", "border-width": 5 },
        },
        {
          selector: "edge[?focal].evidence",
          style: { "line-color": "#edbb69", "target-arrow-color": "#edbb69" },
        },
        {
          selector: ":selected",
          style: {
            "border-width": 4,
            "border-color": "#fff",
            "line-color": "#fff",
            "target-arrow-color": "#fff",
          },
        },
      ],
    });
    cy.current = instance;
    // Keep labels readable at fit-to-screen zoom without changing graph membership.
    const readableLabels = () => {
      const zoom = instance.zoom();
      instance.batch(() => {
        instance.nodes().forEach((node) =>
          node.style({
            "font-size": 12 / zoom,
            width: (node.data("root") ? 38 : 28) / zoom,
            height: (node.data("root") ? 38 : 28) / zoom,
            "text-margin-y": 8 / zoom,
          }),
        );
        instance.edges().style("font-size", 10 / zoom);
      });
    };
    instance.on("zoom", readableLabels);
    readableLabels();

    instance.on("tap", "node", (e) =>
      callback.current({
        kind: "node",
        id: e.target.id(),
        account: [e.target.data("bank"), e.target.data("account")],
      }),
    );
    instance.on("tap", "edge", (e) =>
      callback.current({
        kind: "edge",
        refs: e.target.data("refs"),
        focal: e.target.data("focal"),
      }),
    );
    const observer = new ResizeObserver(() => {
      instance.resize();
    });
    observer.observe(container.current);
    return () => {
      observer.disconnect();
      instance.destroy();
    };
  }, [graph]);
  useEffect(() => {
    const instance = cy.current;
    if (!instance) return;
    instance.elements().unselect().removeClass("evidence muted focused");
    instance.edges().forEach((e) => e.data("displayLabel", e.data("label")));
    if (selection?.kind === "node") {
      const node = instance.getElementById(selection.id);
      node.addClass("focused");
    }
    if (selection?.refs) {
      const ids = new Set(selection.refs);
      const edges = instance
        .edges()
        .filter((e) => e.data("refs").some((id) => ids.has(id)));
      instance.elements().addClass("muted");
      edges.removeClass("muted").addClass("evidence");
      edges.connectedNodes().removeClass("muted").addClass("evidence");
      edges.forEach((e) => {
        const count = e.data("refs").filter((id) => ids.has(id)).length;
        e.data(
          "displayLabel",
          e.data("focal")
            ? "Selected focal transfer"
            : `${count} of ${e.data("refs").length} selected`,
        );
      });
      instance
        .edges()
        .filter((e) => e.data("focal"))
        .removeClass("muted");
      instance
        .nodes()
        .filter((n) => n.data("root"))
        .removeClass("muted");
    }
  }, [selection, graph]);
  return (
    <section className="network panel">
      <div className="panel-heading">
        <div>
          <h2>Connected accounts</h2>
          <p>
            All history retained · amber ring: root · cyan ring: selected
            account
          </p>
        </div>
        <div className="toolbar">
          {onReset && <button onClick={onReset}>Return to full network</button>}
          <button
            onClick={() => cy.current.zoom(cy.current.zoom() * 1.3)}
            aria-label="Zoom in"
          >
            +
          </button>
          <button
            onClick={() => cy.current.zoom(cy.current.zoom() / 1.3)}
            aria-label="Zoom out"
          >
            −
          </button>
          <button onClick={() => cy.current.fit(undefined, 65)}>
            Fit network
          </button>
        </div>
      </div>
      <div
        ref={container}
        className="graph"
        data-testid="network"
        role="img"
        aria-label="Interactive directed transaction network. Select nodes or arrows; account and transfer selectors are also available below."
      />
      <div
        className="graph-counts"
        data-testid="graph-counts"
        data-nodes={graph.historicalNodes + graph.focalOnlyNodes}
        data-edges={graph.relationships + (report.focal ? 1 : 0)}
      >
        <strong>
          {graph.historicalNodes} historical accounts ·{" "}
          {graph.historicalTransfers} historical transfers
        </strong>
        <span>
          {graph.relationships} grouped arrows + {report.focal ? 1 : 0} separate
          selected transfer · {graph.focalOnlyNodes} focal-only accounts
        </span>
      </div>
      {graph.historicalTransfers === 0 && (
        <p className="notice">
          No earlier transfers were returned in this scope. The selected
          transfer alone is not a historical pattern.
        </p>
      )}
      {graph.historicalTransfers > 0 && graph.relationships < 3 && (
        <p className="notice">
          This is a sparse local history. A small network does not establish low
          risk.
        </p>
      )}
      <p className="footnote">
        Drag to pan or reposition accounts; scroll to zoom. Dashed amber =
        selected transfer, not historical evidence. Green = selected evidence; a
        grouped arrow can also contain other transfers. Connections do not
        establish movement of the same funds.
      </p>
    </section>
  );
}
