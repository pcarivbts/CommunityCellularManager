/*
 * Copyright (c) 2016-present, Facebook, Inc.
 * All rights reserved.
 *
 * This source code is licensed under the BSD-style license found in the
 * LICENSE file in the root directory of this source tree. An additional grant
 * of patent rights can be found in the PATENTS file in the same directory.
 */

// React chart components.


var TimeseriesChartWithButtonsAndDatePickers = React.createClass({

  getInitialState: function() {
    // We expect many of these values to be overridden before the chart is
    // first rendered -- see componentDidMount.
    return {
      startTimeEpoch: 0,
      endTimeEpoch: -1,
      isLoading: true,
      chartData: {},
      activeButtonText: '',
      xAxisFormatter: '%x',
      yAxisFormatter: '',
      activeView:''
    }
  },

  getDefaultProps: function() {
    // Load the current time with the user's clock if nothing is specified.  We
    // also specify the user's computer's timezone offset and use that to
    // adjust the graph data.
    var currentTime = Math.round(new Date().getTime() / 1000);
    return {
      chartID: 'one',
      buttons: ['hour', 'day', 'week', 'month', 'year'],
      icons: ['graph', 'list'],
      defaultView: 'graph',
      defaultButtonText: 'week',
      endpoint: '/api/v1/reports/network',
      statTypes: 'sms',
      levelID: 0,
      aggregation: 'count',
      yAxisLabel: 'an axis label (set me!)',
      currentTimeEpoch: currentTime,
      timezoneOffset: 0,
      tooltipUnits: '',
      chartType: 'line-chart'
    }
  },

  // On-mount, build the charts with the default data.
  // Note that we have to load the current time here.
  componentDidMount: function() {
    this.setState({
      activeButtonText: this.props.defaultButtonText,
      activeView: this.props.defaultView,
      startTimeEpoch: this.props.currentTimeEpoch - secondsMap[this.props.defaultButtonText],
      endTimeEpoch: this.props.currentTimeEpoch,
    // When the request params in the state have been set, go get more data.
    }, function() {
      this.updateChartData();
    });
  },

  componentDidUpdate(prevProps, prevState) {
    // Update if we toggled a load
    if (!prevState.isLoading && this.state.isLoading) {
      this.updateChartData();
    }
  },

  // This handler takes the text of the date range buttons
  // and ouputs figures out the corresponding number of seconds.
  handleButtonClick: function(text) {
    // Update only if the startTime has actually changed.
    var newStartTimeEpoch = this.props.currentTimeEpoch - secondsMap[text];
    if (this.state.startTimeEpoch != newStartTimeEpoch) {
      this.setState({
        startTimeEpoch: newStartTimeEpoch,
        endTimeEpoch: this.props.currentTimeEpoch,
        isLoading: true,
        activeButtonText: text,
      });
    }
  },

  // This handler takes the text of the view mode buttons
  // and ouputs figures out the corresponding number of seconds.
  handleViewClick: function(text) {
    console.log("view mode CHANGED = ", text);
    // Update only if the startTime has actually changed.
    if (this.state.activeView != text) {
      this.setState({
        isLoading: true,
        activeView: text
      });
    }
  },

  // Datepicker handlers, one each for changing the start and end times.
  startTimeChange: function(newTime) {
    if (newTime < this.state.endTimeEpoch && !this.state.isLoading) {
      this.setState({
        startTimeEpoch: newTime,
        isLoading: true,
      });
    }
  },
  endTimeChange: function(newTime) {
    var now = moment().unix();
    if (newTime > this.state.startTimeEpoch && newTime < now
        && !this.state.isLoading) {
      this.setState({
        endTimeEpoch: newTime,
        isLoading: true,
      });
    }
  },

  // Gets new chart data from the backend.
  // Recall that this must be called explicitly..it's a bit different
  // than the normal react component connectivity.
  // First figure out how to set the interval (or, more aptly, the bin width)
  // and the x-axis formatter (see the d3 wiki on time formatting).
  updateChartData: function() {
    var interval, newXAxisFormatter, newYAxisFormatter;
    var delta = this.state.endTimeEpoch - this.state.startTimeEpoch;
    if (delta <= 60) {
      interval = 'seconds';
      newXAxisFormatter = '%-H:%M:%S';
    } else if (delta <= (60 * 60)) {
      interval = 'minutes';
      newXAxisFormatter = '%-H:%M';
    } else if (delta <= (24 * 60 * 60)) {
      interval = 'hours';
      newXAxisFormatter = '%-H:%M';
    } else if (delta <= (7 * 24 * 60 * 60)) {
      interval = 'hours';
      newXAxisFormatter = '%b %d, %-H:%M';
    } else if (delta <= (30 * 24 * 60 * 60)) {
      interval = 'days';
      newXAxisFormatter = '%b %d';
    } else if (delta <= (365 * 24 * 60 * 60)) {
      interval = 'days';
      newXAxisFormatter = '%b %d';
    } else {
      interval = 'months';
      newXAxisFormatter = '%x';
    }
    if (this.props.statTypes == 'total_data,uploaded_data,downloaded_data') {
      newYAxisFormatter = '.1f';
    } else {
      newYAxisFormatter = '';
    }
    var queryParams = {
      'start-time-epoch': this.state.startTimeEpoch,
      'end-time-epoch': this.state.endTimeEpoch,
      'interval': interval,
      'stat-types': this.props.statTypes,
      'level-id': this.props.levelID,
      'aggregation': this.props.aggregation,
      'report-view':'summary'
    };
    $.get(this.props.endpoint, queryParams, function(data) {
      this.setState({
        isLoading: false,
        chartData: data,
        xAxisFormatter: newXAxisFormatter,
        yAxisFormatter: newYAxisFormatter,
      });
    }.bind(this));
  },

  render: function() {
    var fromDatepickerID = 'from-datepicker-' + this.props.chartID;
    var toDatepickerID = 'to-datepicker-' + this.props.chartID;
    return (
      <div>
        <div>&nbsp;</div>
        <span>past &nbsp;&nbsp;</span>
        {this.props.buttons.map(function(buttonText, index) {
          return (
            <RangeButton
              buttonText={buttonText}
              activeButtonText={this.state.activeButtonText}
              onButtonClick={this.handleButtonClick}
              key={index}
            />
          );
        }, this)}
        <span className='spacer'></span>
        <DatePicker
          label='from'
          pickerID={fromDatepickerID}
          epochTime={this.state.startTimeEpoch}
          onDatePickerChange={this.startTimeChange}
        />
        <DatePicker
          label='to'
          pickerID={toDatepickerID}
          epochTime={this.state.endTimeEpoch}
          onDatePickerChange={this.endTimeChange}
        />
        <span className='spacer'></span>
        <span>view as&nbsp;&nbsp;&nbsp;</span>
        {this.props.icons.map(function(buttonText, index) {
          return (
            <ViewButton
              buttonText={buttonText}
              activeView={this.state.activeView}
              onButtonClick={this.handleViewClick}
              key={index}
            />
          );
        }, this)}
        <span className='spacer'></span>
        <LoadingText
          visible={this.state.isLoading}
        />
        <DownloadButton />
        <TimeseriesChart
          chartID={this.props.chartID}
          data={this.state.chartData}
          xAxisFormatter={this.state.xAxisFormatter}
          yAxisFormatter={this.state.yAxisFormatter}
          yAxisLabel={this.props.yAxisLabel}
          timezoneOffset={this.props.timezoneOffset}
          tooltipUnits={this.props.tooltipUnits}
          chartType={this.props.chartType}
          activeView={this.state.activeView}
        />
      </div>
    );
  },
});


var secondsMap = {
  'hour': 60 * 60,
  'day': 24 * 60 * 60,
  'week': 7 * 24 * 60 * 60,
  'month': 30 * 24 * 60 * 60,
  'year': 365 * 24 * 60 * 60,
};


// Builds the target chart from scratch.  NVD3 surprisingly handles this well.
// domTarget is the SVG element's parent and data is the info that will be graphed.
var updateChart = function(domTarget, data, xAxisFormatter, yAxisFormatter, yAxisLabel, timezoneOffset, tooltipUnits, chartType) {
  // We pass in the timezone offset and calculate a locale offset.  The former
  // is based on the UserProfile's specified timezone and the latter is the user's
  // computer's timezone offset.  We manually shift the data to work around
  // d3's conversion into the user's computer's timezone.  Note that for my laptop
  // in PST, the locale offset is positive (7hrs) while the UserProfile offset
  // is negative (-7hrs).
  var localeOffset = 60 * (new Date()).getTimezoneOffset();
  var shiftedData = [];
  for (var index in data) {
    var newSeries = { 'key': data[index]['key'] };
    var newValues = [];
    if( typeof(data[index]['values']) === 'object'){
      for (var series_index in data[index]['values']) {
        var newValue = [
          // Shift out of the locale offset to 'convert' to UTC and then shift
          // back into the operator's tz by adding the tz offset from the server.
          data[index]['values'][series_index][0] + 1e3 * localeOffset + 1e3 * timezoneOffset,
          data[index]['values'][series_index][1]
        ];
        newValues.push(newValue);
      }
      newSeries['values'] = newValues;
    } else {
      newSeries['values'] = data[index]['values'];
    }
    shiftedData.push(newSeries);
  }

  
  nv.addGraph(function() {

    if(chartType == 'pie-chart') {
        var chart = nv.models.pieChart()
            .x(function(d) { return d.key.replace('_'," "); })
            .y(function(d) { return d.values; })
            .showLabels(true)
            .labelType("percent");

        d3.select(domTarget)
        .datum(shiftedData)
        .transition().duration(1200)
        .call(chart);

    }
    else if(chartType == 'bar-chart'){
        console.log("BAR CHART");
        //var chart = nv.models.discreteBarChart()
        var chart = nv.models.multiBarChart()
            //.x(function(d) { return d.key; })
            //.y(function(d) { return Math.floor((Math.random() * 100) + 1); })
            .x(function(d) { return d.label })    //Specify the data accessors.
            .y(function(d) { return d.value })
            //.staggerLabels(false)    //Too many bars and not enough room? Try staggering labels.
            //.tooltips(true)        //Don't show tooltips
            //.showValues(true)       //...instead, show the bar value right on top of each bar.
            .transitionDuration(350);
            //.color(d3.scale.category10().range());
            //.showControls(true);

        d3.select(domTarget)
            .datum(exampleData())
            //.datum(shiftedData)
            .transition().duration(350)
            .call(chart);
    } else {
        var chart = nv.models.lineChart()
          .x(function(d) { return d[0] })
          .y(function(d) { return d[1] })
          .color(d3.scale.category10().range())
          .interpolate('monotone')
          .showYAxis(true)
          ;
        chart.xAxis
          .tickFormat(function(d) {
            return d3.time.format(xAxisFormatter)(new Date(d));
          });
        // Fixes x-axis time alignment.
        chart.xScale(d3.time.scale.utc());
        chart.yAxis
          .axisLabel(yAxisLabel)
          .axisLabelDistance(25)
          .tickFormat(d3.format(yAxisFormatter));
        // Fixes the axis-labels being rendered out of the SVG element.
        chart.margin({right: 80});
        chart.tooltipContent(function(key, x, y) {
          return '<p>' + y + tooltipUnits + ' ' + key + '</p>' + '<p>' + x + '</p>';
        });

        d3.select(domTarget)
            .datum(shiftedData)
            .transition().duration(350)
            .call(chart);

    }
    // Resize the chart on window resize.
    nv.utils.windowResize(chart.update);
    return chart;
  });
};


var TimeseriesChart = React.createClass({

  getDefaultProps: function() {
    return {
      chartID: 'some-chart-id',
      chartHeight: 380,
      data: {},
      xAxisFormatter: '%x',
      yAxisFormatter: '',
      yAxisLabel: 'the y axis!',
      timezoneOffset: 0,
      tooltipUnits: '',
      chartType:'',
      activeView:''
    }
  },

  chartIsFlat(results) {
    return results.every(function(series) {
      if(typeof(series['values']) === 'object'){
        return series['values'].every(function(pair) {
          return pair[1] === 0;
        });
      } else {
        return series['values'] === 0;
      }
    });
  },

  render: function() {
    var results = this.props.data['results'];
    var isFlatChart = !results || this.chartIsFlat(results);
    var className = ['time-series-chart-container'];
    var flatLineOverlay = null;
    if (isFlatChart) {
      flatLineOverlay = (
        <div className='flat-chart-overlay'
             style={{height: this.props.chartHeight}}>
          <div style={{"line-height": this.props.chartHeight - 20}}>
            No data available for this range.
          </div>
        </div>
      );
      className.push('flat');
    }
    return (
      <div className={className.join(' ')}>
        {flatLineOverlay}
        <TimeSeriesChartElement {...this.props}/>
      </div>
    );
  }
});


var TimeSeriesChartElement = React.createClass({
  // When the request params have changed, get new data and rebuild the graph.
  // We circumvent react's typical re-render cycle for this component by returning false.
  shouldComponentUpdate: function(nextProps) {
    this.props.activeView = nextProps.activeView;

    console.log("nextProps = ", nextProps);
    console.log("activeView = ", nextProps.activeView, this.props.activeView);
    console.log("this.props.chartType = ", this);

    var nextData = JSON.stringify(nextProps.data);
    var prevData = JSON.stringify(this.props.data);
    if (nextData !== prevData) {
      updateChart(
        '#' + this.props.chartID,
        nextProps.data['results'],
        nextProps.xAxisFormatter,
        nextProps.yAxisFormatter,
        nextProps.yAxisLabel,
        this.props.timezoneOffset,
        this.props.tooltipUnits,
        this.props.chartType
      );
    }
    return false;
  },

  render: function() {
    console.log("this.props = ", this.props);
    var inlineStyles = {
      height: this.props.chartHeight
    };
    if(this.props.activeView == 'list') {

      var cols = [
            { key: 'firstName', label: 'First Name' },
            { key: 'lastName', label: 'Last Name' }
        ];

        var data = [
            { id: 1, firstName: 'John', lastName: 'Doe' },
            { id: 2, firstName: 'Clark', lastName: 'Kent' }
        ];


      d3.select('#call-chart').selectAll('svg').remove();
      return (
        <Table cols={cols} data={data}/>
      );

    } else {
      return (
        <svg id={this.props.chartID}
             className="time-series-chart"
             style={inlineStyles}>
        </svg>
      );
    }
  }
});


var RangeButton = React.createClass({
  propTypes: {
    buttonText: React.PropTypes.string.isRequired
  },

  getDefaultProps: function() {
    return {
      buttonText: 'day',
      activeButtonText: '',
      onButtonClick: null,
    }
  },

  render: function() {
    // Determine whether this particular button is active by checking
    // this button's text vs the owner's knowledge of the active button.
    // Then change styles accordingly.
    var inlineStyles = {
      marginRight: 20
    };
    if (this.props.buttonText == this.props.activeButtonText) {
      inlineStyles.cursor = 'inherit';
      inlineStyles.color = 'black';
      inlineStyles.textDecoration = 'none';
    } else {
      inlineStyles.cursor = 'pointer';
    }
    return (
      <a style={inlineStyles} onClick={this.onThisClick.bind(this, this.props.buttonText)}>
        {this.props.buttonText}
      </a>
    );
  },

  onThisClick: function(text) {
    this.props.onButtonClick(text);
  },
});


var LoadingText = React.createClass({
  getDefaultProps: function() {
    return {
      visible: false,
    }
  },

  render: function() {
    var inlineStyles = {
      display: this.props.visible ? 'inline' : 'none',
      marginRight: 20,
    };

    return (
      <span className="loadingText" style={inlineStyles}>
        (loading..)
      </span>
    );
  },
});


var DatePicker = React.createClass({
  getDefaultProps: function() {
    return {
      label: 'date',
      pickerID: 'some-datetimepicker-id',
      epochTime: 0,
      onDatePickerChange: null,
      datePickerOptions : {
        icons: {
          time: 'fa fa-clock-o',
          date: 'fa fa-calendar',
          up: 'fa fa-arrow-up',
          down: 'fa fa-arrow-down',
          previous: 'fa fa-arrow-left',
          next: 'fa fa-arrow-right',
          today: 'fa fa-circle-o',
        },
        showTodayButton: true,
        format: 'YYYY-MM-DD [at] h:mmA',
      },
      dateFormat: 'YYYY-MM-DD [at] h:mmA',
    }
  },

  componentDidMount: function() {
    var formattedDate = moment.unix(this.props.epochTime).format(this.props.dateFormat);
    var domTarget = '#' + this.props.pickerID;
    $(domTarget)
      .datetimepicker(this.props.datePickerOptions)
      .data('DateTimePicker')
      .date(formattedDate);
    var dateFormat = this.props.dateFormat;
    var handler = this.props.onDatePickerChange;
    $(domTarget).on('dp.change', function(event) {
      var newEpochTime = moment(event.target.value, dateFormat).unix();
      handler(newEpochTime);
    });
  },

  shouldComponentUpdate: function(nextProps) {
    var formattedDate = moment.unix(nextProps.epochTime).format(nextProps.dateFormat);
    var domTarget = '#' + nextProps.pickerID;
    $(domTarget).data('DateTimePicker').date(formattedDate);
    return false
  },

  render: function() {
    return (
      <span className='datepicker'>
        <label>{this.props.label}</label>
        <input id={this.props.pickerID} type="text" />
      </span>
    );
  },
});


var DownloadButton = React.createClass({
  getDefaultProps: function() {
    return {
      visible: false,
    }
  },

  render: function() {
    return (
      <span className="loadingText pull-right">
        download&nbsp;&nbsp; 
        <a href="javascript:void(0);" title="download graph">
          <i className='fa fa-lg fa-area-chart' aria-hidden="true"></i>
        </a>&nbsp;&nbsp;
        <a href="javascript:void(0);" title="download CSV">
          <i className='fa fa-lg fa-list-ul' aria-hidden="true"></i>
        </a>
      </span>
    );
  },
});


var ViewButton = React.createClass({
  propTypes: {
    buttonText: React.PropTypes.string.isRequired
  },

  getDefaultProps: function() {
    return {
      buttonText: 'graph',
      activeView: '',
      onButtonClick: null,
    }
  },

  render: function() {
    // Determine whether this particular button is active by checking
    // this button's text vs the owner's knowledge of the active button.
    // Then change styles accordingly.
    var inlineStyles = {
      marginRight: 20
    };
    if (this.props.buttonText == this.props.activeView) {
      inlineStyles.cursor = 'inherit';
      inlineStyles.color = 'black';
      inlineStyles.textDecoration = 'none';
    } else {
      inlineStyles.cursor = 'pointer';
    }
    if(this.props.buttonText == 'graph') {
      return (
        <a style={inlineStyles} onClick={this.onThisClick.bind(this, this.props.buttonText)}  title="view as graph">
          <i className='fa fa-lg fa-area-chart' aria-hidden="true"></i>
        </a>
      );
    } else {
      return (
        <a style={inlineStyles} onClick={this.onThisClick.bind(this, this.props.buttonText)}  title="view as table">
          <i className='fa fa-lg fa-list-ul' aria-hidden="true"></i>
        </a>
      );
    }
  },

  onThisClick: function(text) {
    this.props.onButtonClick(text);
  },
});


















function exampleData() {
 return  [
    {
      key: "Cumulative Return",
      values: [
        {
          "label" : "A Label" ,
          "value" : 29.765957771107
        } ,
        {
          "label" : "B Label" ,
          "value" : 0
        } ,
        {
          "label" : "C Label" ,
          "value" : 32.807804682612
        } ,
        {
          "label" : "D Label" ,
          "value" : 196.45946739256
        } ,
        {
          "label" : "E Label" ,
          "value" : 0.19434030906893
        } ,
        {
          "label" : "F Label" ,
          "value" : 98.079782601442
        } ,
        {
          "label" : "G Label" ,
          "value" : 13.925743130903
        } ,
        {
          "label" : "H Label" ,
          "value" : 5.1387322875705
        }
      ]
    },
    {
      key: "Second",
      values: [
        {
          "label" : "AA" ,
          "value" : 196.45946739256
        } ,
        {
          "label" : "BB" ,
          "value" : 0.19434030906893
        } ,
        {
          "label" : "CC" ,
          "value" : 98.079782601442
        } ,
        {
          "label" : "DD" ,
          "value" : 13.925743130903
        } ,
        {
          "label" : "EE" ,
          "value" : 5.1387322875705
        }, {
          "label" : "FF" ,
          "value" : 29.765957771107
        } ,
        {
          "label" : "GG" ,
          "value" : 0
        } ,
        {
          "label" : "HH" ,
          "value" : 32.807804682612
        }
      ]
    }, {
      key: "Third",
      values: [
        {
          "label" : "AA Label" ,
          "value" : 29.765957771107
        } ,
        {
          "label" : "BB Label" ,
          "value" : 0
        } ,
        {
          "label" : "CC Label" ,
          "value" : 32.807804682612
        } ,
        {
          "label" : "DD Label" ,
          "value" : 196.45946739256
        } ,
        {
          "label" : "EE Label" ,
          "value" : 0.19434030906893
        } ,
        {
          "label" : "FF Label" ,
          "value" : 98.079782601442
        } ,
        {
          "label" : "GG Label" ,
          "value" : 13.925743130903
        } ,
        {
          "label" : "HH Label" ,
          "value" : 5.1387322875705
        }
      ]
    }
  ]

}



var cols = [
    { key: 'firstName', label: 'First Name' },
    { key: 'lastName', label: 'Last Name' }
];

var data = [
    { id: 1, firstName: 'John', lastName: 'Doe' },
    { id: 2, firstName: 'Clark', lastName: 'Kent' }
];

var Table = React.createClass({

    render: function() {
        var headerComponents = this.generateHeaders(),
            rowComponents = this.generateRows();

        return (
            <table className='table table-striped table-bordered'>
                <thead> {headerComponents} </thead>
                <tbody> {rowComponents} </tbody>
            </table>
        );
    },

    generateHeaders: function() {
        var cols = this.props.cols;  // [{key, label}]

        // generate our header (th) cell components
        return cols.map(function(colData) {
            return <th key={colData.key}> {colData.label} </th>;
        });
    },

    generateRows: function() {
        var cols = this.props.cols,  // [{key, label}]
            data = this.props.data;

        return data.map(function(item) {
            // handle the column data within each row
            var cells = cols.map(function(colData) {

                // colData.key might be "firstName"
                return <td> {item[colData.key]} </td>;
            });
            return <tr key={item.id}> {cells} </tr>;
        });
    }
});