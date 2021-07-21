import numpy as np
import panel as pn
from bokeh.models import (
    BasicTickFormatter,
    ColumnDataSource,
    FixedTicker,
    FuncTickFormatter,
    LinearAxis,
    LinearColorMapper,
    MultiLine,
    Range1d,
    TapTool,
    WheelZoomTool,
    Rect,
    Model,
)
from bokeh.core.enums import LineDash, LineCap, MarkerType, NamedColor
from bokeh.models.plots import _list_attr_splat
from bokeh.plotting import figure

from ..models import PCPSelectionTool, PCPResetTool, PCPBoxAnnotation


def _parallel_plot(df_raw, drop=None, color=None, palette=None):
    """From a dataframe create a parallel coordinate plot"""
    if drop is not None:
        df = df_raw.drop(drop, axis=1)
    else:
        df = df_raw.copy()
    npts = df.shape[0]
    ndims = len(df.columns)

    if color is None:
        color = np.ones(npts)
    if palette is None:
        palette = ["#ff0000"]
    if color.dtype == np.object_:
        color = color.apply(lambda elem: np.where(color.unique() == elem)[0].item())
    cmap = LinearColorMapper(high=color.min(), low=color.max(), palette=palette)
    categorical_columns = df.columns.where(df.dtypes == np.object_).dropna()
    for col in categorical_columns:
        df[col] = df[col].apply(
            lambda elem: np.where(df[col].unique() == elem)[0].item()
        )

    data_source = ColumnDataSource(
        dict(
            xs=np.arange(ndims)[None, :].repeat(npts, axis=0).tolist(),
            ys=np.array((df - df.min()) / (df.max() - df.min())).tolist(),
            color=color,
        )
    )

    p = figure(
        x_range=(-1, ndims),
        y_range=(0, 1),
        width=1000,
        tools="pan, box_zoom",
        output_backend="webgl",
    )

    # Create x axis ticks from columns contained in dataframe
    fixed_x_ticks = FixedTicker(ticks=np.arange(ndims), minor_ticks=[])
    formatter_x_ticks = FuncTickFormatter(
        code="return columns[index]", args={"columns": df.columns}
    )
    p.xaxis.ticker = fixed_x_ticks
    p.xaxis.formatter = formatter_x_ticks

    p.yaxis.visible = False
    p.y_range.start = 0
    p.y_range.end = 1
    p.y_range.bounds = (-0.1, 1.1)  # add a little padding around y axis
    p.xgrid.visible = False
    p.ygrid.visible = False

    # Create extra y axis for each dataframe column
    tickformatter = BasicTickFormatter(precision=1)
    for index, col in enumerate(df.columns):
        start = df[col].min()
        end = df[col].max()
        bound_min = start + abs(end - start) * (p.y_range.bounds[0] - p.y_range.start)
        bound_max = end + abs(end - start) * (p.y_range.bounds[1] - p.y_range.end)
        range1d = Range1d(start=bound_min, end=bound_max, bounds=(bound_min, bound_max))
        p.extra_y_ranges.update({col: range1d})
        if col not in categorical_columns:
            fixedticks = FixedTicker(ticks=np.linspace(start, end, 8), minor_ticks=[])
            major_label_overrides = {}
        else:
            fixedticks = FixedTicker(ticks=np.arange(end + 1), minor_ticks=[])
            major_label_overrides = {
                i: str(name) for i, name in enumerate(df_raw[col].unique())
            }

        p.add_layout(
            LinearAxis(
                fixed_location=index,
                y_range_name=col,
                ticker=fixedticks,
                formatter=tickformatter,
                major_label_overrides=major_label_overrides,
            ),
            "right",
        )

    # create the data renderer ( MultiLine )
    # specify selected and non selected style
    non_selected_line_style = dict(line_color="grey", line_width=0.1, line_alpha=0.5)

    selected_line_style = dict(
        line_color={"field": "color", "transform": cmap}, line_width=1
    )

    parallel_renderer = p.multi_line(
        xs="xs", ys="ys", source=data_source, **non_selected_line_style
    )

    # Specify selection style
    selected_lines = MultiLine(**selected_line_style)

    # Specify non selection style
    nonselected_lines = MultiLine(**non_selected_line_style)

    parallel_renderer.selection_glyph = selected_lines
    parallel_renderer.nonselection_glyph = nonselected_lines
    p.y_range.start = p.y_range.bounds[0]
    p.y_range.end = p.y_range.bounds[1]

    rect_source = ColumnDataSource({"x": [], "y": [], "width": [], "height": []})

    rect_glyph = Rect(
        x="x",
        y="y",
        width="width",
        height="height",
        fill_alpha=0.7,
        fill_color="#009933",
    )
    selection_renderer = p.add_glyph(rect_source, rect_glyph)

    overlay = PCPBoxAnnotation(
        level="overlay",
        top_units="screen",
        left_units="screen",
        bottom_units="screen",
        right_units="screen",
        fill_color="lightgrey",
        fill_alpha=0.5,
        line_color="black",
        line_alpha=1.0,
        line_width=2,
        line_dash=[4, 4],
    )
    selection_tool = PCPSelectionTool(
        renderer_select=selection_renderer,
        renderer_data=parallel_renderer,
        box_width=10,
        overlay=overlay,
    )
    # custom resets (reset only axes not selections)
    reset_axes = PCPResetTool()

    # add tools and activate selection ones
    p.add_tools(selection_tool, reset_axes, TapTool(), WheelZoomTool())
    p.toolbar.active_drag = selection_tool
    p.toolbar.active_tap = None
    return p


def _meta_widgets(model, **kwargs):
    tabs = pn.Tabs(**kwargs)
    widgets = _get_widgets(model)
    if widgets:
        tabs.append((type(model).__name__, widgets))
    for p, v in model.properties_with_values().items():
        if isinstance(v, _list_attr_splat):
            v = v[0]
        if isinstance(v, Model):
            subtabs = _meta_widgets(v, **kwargs)
            if subtabs is not None:
                tabs.append((p.title(), subtabs))

    if hasattr(model, "renderers"):
        if model.renderers != "auto":
            for r in model.renderers:
                tabs.append((type(r).__name__, _meta_widgets(r, **kwargs)))
    if hasattr(model, "axis") and isinstance(model.axis, list):
        for pre, axis in zip("XY", model.axis):
            tabs.append(("%s-Axis" % pre, _meta_widgets(axis, **kwargs)))
    if hasattr(model, "grid"):
        for pre, grid in zip("XY", model.grid):
            tabs.append(("%s-Grid" % pre, _meta_widgets(grid, **kwargs)))
    if not widgets and not len(tabs) > 0:
        return None
    elif not len(tabs) > 1:
        return tabs[0]
    return tabs


def _get_widgets(model, skip_none=True, **kwargs):
    widgets = []

    print
    for p, v in model.properties_with_values().items():
        if isinstance(v, dict):
            if "value" in v:
                v = v.get("value")
            else:
                continue
        if v is None and skip_none:
            continue

        ps = dict(name=p, value=v, **kwargs)
        if "alpha" in p:
            w = pn.widgets.FloatSlider(start=0, end=1, **ps)
        elif "color" in p:
            if v in list(NamedColor):
                w = pn.widgets.Select(options=list(NamedColor), **ps)
            else:
                w = pn.widgets.ColorPicker(**ps)
        elif p.endswith("width"):
            w = pn.widgets.FloatSlider(start=0, end=20, **ps)
        elif "marker" in p:
            w = pn.widgets.Select(name=p, options=list(MarkerType), value=v)
        elif p.endswith("cap"):
            w = pn.widgets.Select(name=p, options=list(LineCap), value=v)
        elif p == "size":
            w = pn.widgets.FloatSlider(start=0, end=20, **ps)
        elif p.endswith("text") or p.endswith("label"):
            w = pn.widgets.TextInput(**ps)
        elif p.endswith("dash"):
            patterns = list(LineDash)
            if not isinstance(v, list):
                w = pn.widgets.Select(name=p, options=patterns, value=v or patterns[0])
            else:
                continue
        else:
            continue
        w.jslink(model, value=p)
        widgets.append(w)
    return pn.Column(*sorted(widgets, key=lambda w: w.name))