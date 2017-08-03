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
            activeView:'',
            tablesColumnValueName:''
        }
    },
    getDefaultProps: function() {
        // Load the current time with the user's clock if nothing is specified.  We
        // also specify the user's computer's timezone offset and use that to
        // adjust the graph data.
        var currentTime = Math.round(new Date().getTime() / 1000);
        return {
            title: 'title (set me!)',
            chartID: 'one',
            buttons: ['hour', 'day', 'week', 'month', 'year'],
            icons: ['graph', 'list'],
            defaultView: 'graph',
            defaultButtonText: 'week',
            endpoint: '/api/v1/stats/',
            statTypes: 'sms',
            level: 'network',
            levelID: 0,
            aggregation: 'count',
            yAxisLabel: 'an axis label (set me!)',
            currentTimeEpoch: currentTime,
            timezoneOffset: 0,
            tooltipUnits: '',
            frontTooltip: '',
            chartType: 'line-chart',
            reportView: 'list',
            info: 'info of report type'
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
    handleViewClick: function(text) {
        // Update only if the startTime has actually changed.
        if (this.state.activeView != text) {
            this.setState({
                startTimeEpoch: this.state.startTimeEpoch,
                endTimeEpoch: this.props.currentTimeEpoch,
                isLoading: true,
                activeView: text,
            });
        }
    },

    handleDownloadClick: function(text) {
        var queryParams = {
            'start-time-epoch': this.state.startTimeEpoch,
            'end-time-epoch': this.state.endTimeEpoch,
            'stat-types': this.props.statTypes,
            'level':this.props.level,
            'level_id': this.props.levelID,
            'report-type':this.props.title,
        };
        $.get('/report/downloadcsv', queryParams, function(data,response) {
            var todayTime = new Date(); var month = (todayTime .getMonth() + 1); var day = (todayTime .getDate()); var year = (todayTime .getFullYear());
            var convertdate =  year+ "-" +  month + "-" +day;
            this.setState({
                isLoading: false,
                data: data,
                title:this.props.title
            });
            var filename = this.state.title
            var csvData = new Blob([data], {type: 'text/csv;charset=utf-8;'});
            var csvURL =  null;
            if (navigator.msSaveBlob) {
                csvURL = navigator.msSaveBlob(csvData, filename+"-"+convertdate+'.csv');
            } else {
                csvURL = window.URL.createObjectURL(csvData);
            }
            var tempLink = document.createElement('a');
            document.body.appendChild(tempLink);
            tempLink.href = csvURL;
            tempLink.setAttribute('download', filename+"-"+convertdate+'.csv');
            tempLink.target="_self"
            tempLink.click();
        }.bind(this));
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
        if (newTime > this.state.startTimeEpoch && newTime < now && !this.state.isLoading) {
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
        var interval, newXAxisFormatter, newYAxisFormatter, tablesColumnValueName;
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
        if (this.props.chartID == 'data-chart') {
            newYAxisFormatter = '.2f';
            tablesColumnValueName = [{
                title: "Type"
            }, {
                title: "Minutes"
            }]

        } else if (this.props.chartID == 'call-chart' | this.props.chartID == 'sms-chart') {
            tablesColumnValueName = [{
                title: "Type"
            }, {
                title: "Count"
            }]
        } else if (this.props.chartID == 'topupSubscriber-chart') {
            newYAxisFormatter = '.2f';
            tablesColumnValueName = [{
                title: "Denomination Bracket"
            }, {
                title: "Amount in"
            }]

        } else if (this.props.chartID == 'topup-chart') {
            newYAxisFormatter = '.2f';
            tablesColumnValueName = [{
                title: "Denomination Bracket"
            }, {
                title: "Count"
            }]

        } else if (this.props.chartID == 'load-transfer-chart') {
            newYAxisFormatter = '.2f';
        }
        else {
            tablesColumnValueName = [{
                title: "Type"
            }, {
                title: "Count"
            }]
        }
        var queryParams = {
            'start-time-epoch': this.state.startTimeEpoch,
            'end-time-epoch': this.state.endTimeEpoch,
            'interval': interval,
            'stat-types': this.props.statTypes,
            'level-id': this.props.levelID,
            'aggregation': this.props.aggregation,
            'extras': this.props.extras,
            'dynamic-stat': this.props.dynamicStat,
            'topup-percent': this.props.topupPercent,
            'report-view': this.props.reportView
        };
        var endpoint = this.props.endpoint + this.props.level;
        $.get(endpoint, queryParams, function(data) {
            this.setState({
                isLoading: false,
                chartData: data,
                xAxisFormatter: newXAxisFormatter,
                yAxisFormatter: newYAxisFormatter,
                tablesColumnValueName: tablesColumnValueName,
            });
        }.bind(this));
    },

    render: function() {
        var fromDatepickerID = 'from-datepicker-' + this.props.chartID;
        var toDatepickerID = 'to-datepicker-' + this.props.chartID;
        return (
            <div>
                <h4>
                    {this.props.title}
                    &nbsp; <a rel="tooltip" className='glyphicon glyphicon-info-sign' data-toggle="tooltip" data-placement="right" background-color='#483D8B' title={this.props.info}></a>
                </h4>
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
                <span>&nbsp;&nbsp;&nbsp;</span>
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
                <DownloadButton
                  chartID={this.props.chartID}
                  startimeepoch = {this.props.starttime}
                  endTimeEpoch = {this.props.endTimeEpoch}
                  statsType = {this.props.statTypes}
                  reporttype = {this.props.title}
                  activeView = {this.props.activeView}
                  onButtonClick={this.handleDownloadClick} />
                <span className='spacer'></span>
                <LoadingText
                  visible={this.state.isLoading}
                />
                <TimeseriesChart
                  chartID={this.props.chartID}
                  data={this.state.chartData}
                  xAxisFormatter={this.state.xAxisFormatter}
                  yAxisFormatter={this.state.yAxisFormatter}
                  yAxisLabel={this.props.yAxisLabel}
                  timezoneOffset={this.props.timezoneOffset}
                  tooltipUnits={this.props.tooltipUnits}
                  frontTooltip={this.props.frontTooltip}
                  chartType={this.props.chartType}
                  activeView={this.state.activeView}
                  tablesColumnValueName={this.state.tablesColumnValueName}
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

var add = function (a, b){
  return a + b ;
}

// Builds the target chart from scratch.  NVD3 surprisingly handles this well.
// domTarget is the SVG element's parent and data is the info that will be graphed.
var updateChart = function(domTarget, data, xAxisFormatter, yAxisFormatter, yAxisLabel, timezoneOffset, tooltipUnits, frontTooltip, chartType, domTargetId, tablesColumnValueName) {
    // We pass in the timezone offset and calculate a locale offset.  The former
    // is based on the UserProfile's specified timezone and the latter is the user's
    // computer's timezone offset.  We manually shift the data to work around
    // d3's conversion into the user's computer's timezone.  Note that for my laptop
    // in PST, the locale offset is positive (7hrs) while the UserProfile offset
    // is negative (-7hrs).
    var localeOffset = 60 * (new Date()).getTimezoneOffset();
    var shiftedData = [];
    var changeAmount = [];
    var tableData = [];


    for (var index in data) {
        var newSeries = {
            'key': data[index]['key']
        };
        var retailer = data[index]['retailer_table_data']

        var newValues = [];
        if (typeof(data[index]['values']) === 'object') {
            for (var series_index in data[index]['values']) {

                var newValue = [
                    moment(data[index]['values'][series_index][0] ),
                    data[index]['values'][series_index][1]
                ];
                newValues.push(newValue);
                changeAmount.push(newValue[1])
            }
            // Get sum of the total charges
            var sumAmount = changeAmount.reduce(add, 0);
            changeAmount = []
                // sum can be of all negative values
            if (sumAmount < 0) {
                newSeries['total'] = (sumAmount * -1);
            } else {
                newSeries['total'] = (sumAmount);
            }
            newSeries['values'] = newValues;
        } else {
            newSeries['total'] = data[index]['values'];
        }
        // Get sum of the total charges


        if ( domTargetId == 'call-sms-chart' || domTargetId == 'sms-chart' || domTargetId == 'call-chart' ) {
            if (newSeries['total'] != undefined) {
                newSeries['total'] = newSeries['total']
                tableData.push([newSeries['key'], newSeries['total']]);
            }}
            else if (domTargetId == 'data-chart' || domTargetId == 'topupSubscriber-chart' || domTargetId == 'call-billing-chart' || domTargetId == 'sms-billing-chart' || domTargetId == 'call-sms-billing-chart'){

              if (newSeries['total'] != undefined) {
                newSeries['total'] = newSeries['total'].toFixed(2);
                tableData.push([newSeries['key'], newSeries['total']]);
            }
            }
            else if (domTargetId == 'load-transfer-chart' || domTargetId == 'add-money-chart') {
            if (typeof(retailer !== 'undefined') && Object.keys(retailer).length >= 1) {
                if (Object.keys(retailer).length >= 1) {
                    for (var series_index in data[index]['retailer_table_data']) {
                        var elements = data[index]['retailer_table_data'][series_index];
                        tableData.push([series_index, elements])
                    }
                }
            } else {
                tableData.push(['No data', 'No data'])
            }
        }   else {
                newSeries['total'] = newSeries['total']
                tableData.push([newSeries['key'], newSeries['total']]);
        }

        shiftedData.push(newSeries);
        if (frontTooltip != "" && domTargetId == 'topupSubscriber-chart') {
            tablesColumnValueName = [{
                title: "Denomination Bracket"
            }, {
                title: "Amount in (" + frontTooltip + ")"
            }]
        } else if (domTargetId == 'call-billing-chart' || domTargetId == 'sms-billing-chart' || domTargetId == 'call-sms-billing-chart') {
            tablesColumnValueName = [{
                title: "Type"
            }, {
                title: "Amount in (" + frontTooltip + ")"
            }]
         }
           else if (frontTooltip != "" && domTargetId == 'add-money-chart' || domTargetId == 'load-transfer-chart') {
            tablesColumnValueName = [{
                title: "IMSI"
            }, {
                title: "Amount in (" + frontTooltip + ")"
            }]
        } else {
            tablesColumnValueName = tablesColumnValueName
        }
    }

    $('.' + domTargetId).DataTable({
        data: tableData,
        paging: false,
        ordering: false,
        info: false,
        searching: false,
        autoWidth: true,
        scrollY: 320,
        destroy: true,
        columns: tablesColumnValueName
    });

    nv.addGraph(function() {
        if (chartType == 'pie-chart') {
            var chart = nv.models.pieChart()
                .x(function(d) {
                    return d.key.replace(/[_]/g, ' ');
                })
                .y(function(d) {
                    return d.total;
                })
                .showLabels(true)
                .labelType("percent");

            chart.tooltipContent(function(key, x, y) {
                chart.valueFormat(d3.format(yAxisFormatter));
                return '<p><h3>' + key + '</p></h3>' + '<center>' + '<b>' + '<h4>' + frontTooltip + x + '</center>' + '</b>' + '<h4>'
            });

            d3.select(domTarget)
                .datum(shiftedData)
                .transition().duration(350)
                .call(chart);
        } else if (chartType == 'bar-chart') {

            var chart = nv.models.multiBarChart()
                .x(function(d) {
                    return d[0]
                })
                .y(function(d) {
                    return d[1]
                })
                .color(d3.scale.category10().range())
                .options({
                interpolate: 'monotone',
                 grid:true //<== this line here
                })
                .showYAxis(true)
                .stacked(false).showControls(false)
                .reduceXTicks(true)
                ;
                chart.xAxis
                  .scale( d3.time.scale.utc())
                  .showMaxMin(true);
                chart.xAxis
                     .tickFormat(function(d){return d3.time.format(xAxisFormatter)(new Date(d));})
                 chart.yAxis
                  .axisLabel(yAxisLabel)
                  .axisLabelDistance(25)
                  .tickFormat(d3.format(yAxisFormatter));
            // Fixes the axis-labels being rendered out of the SVG element.
            chart.margin({
                right: 90
            });
            chart.tooltipContent(function(key, x, y) {
                if (key == 'add_money') {
                    return '<p>' + frontTooltip + y + tooltipUnits + ' ' + '</p>' + '<p>' + x + '</p>';
                } else {
                    return '<p>' + frontTooltip + y + tooltipUnits + ' ' + key + '</p>' + '<p>' + x + '</p>';
                }
            });
                d3.select(domTarget)
                .datum(shiftedData)
                .transition().duration(350)
                .call(chart);

        } else {
            var chart = nv.models.lineChart()
                .x(function(d) {
                    return d[0]
                })
                .y(function(d) {
                if (d[1] > 0){
                    return 1
                } else {
                    return 0
                }

                })
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
            // For Health Graph
            if(domTarget == '#call-chart') {
                chart.yAxis
                .axisLabel(yAxisLabel)
                .axisLabelDistance(25)
                 .tickFormat(function(d) {
                    if (d == 1){
                        return "UP";
                    } else if (d > 0) {
                        return ;
                    } else {
                        return "DOWN";
                        }
                    });
            } else {
                chart.yAxis
                .axisLabel(yAxisLabel)
                .axisLabelDistance(25)
                .tickFormat(d3.format(yAxisFormatter));
            }

            // Fixes the axis-labels being rendered out of the SVG element.
            chart.margin({
                right: 80
            });
            chart.tooltipContent(function(key, x, y) {
                if (key == 'health_state') {
                    key = ''
                    if (y =='UP'){
                        y = '<span class = "label label-success">UP</span>'
                    } else {
                        y = '<span class = "label label-danger">DOWN</span>'
                    }
                }
                return '<p>' + frontTooltip + y + tooltipUnits + ' ' + key + '</p>' + '<p>' + x + '</p>';
            });

            d3.selectAll(".nv-axis path").style({ 'fill':'none', 'stroke': '#000' });
            d3.selectAll(".nv-chart path").style({ 'fill':'none'});
            d3.selectAll(".nv-line").style({ 'fill':'none'});

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
            frontTooltip: '',
            tooltipUnits: '',
            chartType:'',
            activeView:'',
            tablesColumnValueName:''
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
                <div className='flat-chart-overlay' style={{height: this.props.chartHeight}}>
                    <div style={{"line-height": this.props.chartHeight - 20}}>
                        No data available for this range.
                    </div>
                </div>
            );
            className.push('flat');
        }
        if(this.props.activeView == 'list') {
            $('#'+this.props.chartID + "-download").hide();
            return (
                <div className={className.join(' ')}>
                    {flatLineOverlay}
                    <Table {...this.props}/>
                </div>
            );
        } else {
            $('#'+this.props.chartID + "-download").show();
            return (
                <div className={className.join(' ')}>
                    {flatLineOverlay}
                    <TimeSeriesChartElement {...this.props}/>
                </div>
            );
        }
    }
});


var TimeSeriesChartElement = React.createClass({
    // When the request params have changed, get new data and rebuild the graph.
    // We circumvent react's typical re-render cycle for this component by returning false.
    shouldComponentUpdate: function(nextProps) {
        this.props.activeView = nextProps.activeView;
        var nextData = JSON.stringify(nextProps.data);
        var prevData = JSON.stringify(this.props.data);
        this.forceUpdate();
        if (nextData !== prevData) {
            updateChart(
                '#' + this.props.chartID,
                nextProps.data['results'],
                nextProps.xAxisFormatter,
                nextProps.yAxisFormatter,
                nextProps.yAxisLabel,
                this.props.timezoneOffset,
                this.props.tooltipUnits,
                this.props.frontTooltip,
                this.props.chartType,
                this.props.chartID,
                nextProps.tablesColumnValueName
            );
        }
        return false;
    },
    componentDidUpdate(prevProps, prevState) {
        var nextProps = prevProps;
        // Update if we toggled a load
        updateChart(
            '#' + this.props.chartID,
            nextProps.data['results'],
            nextProps.xAxisFormatter,
            nextProps.yAxisFormatter,
            nextProps.yAxisLabel,
            this.props.timezoneOffset,
            this.props.tooltipUnits,
            this.props.frontTooltip,
            this.props.chartType,
            this.props.chartID,
            nextProps.tablesColumnValueName
        );
    },
    render: function() {
        var inlineStyles = {
            height: this.props.chartHeight
        };
        return (
            <svg id={this.props.chartID}
                className="time-series-chart"
                style={inlineStyles}>
            </svg>
        );
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
            display: this.props.visible ? 'inline' : 'none', marginRight: 20
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
            datePickerOptions: {
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
        $(domTarget).keydown(function(e) {
            e.preventDefault();
            return false;
        });
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
            startimeepoch:'',
            endTimeEpoch:'',
            defaultButtonText: 'week',
            statsType:'',
            onButtonClick: null,
            activeView:'graph'
        }
    },
    componentWillMount() {
        this.id = this.props.chartID + "-download";
    },
    componentDidMount: function() {
        var domTargetId = this.props.chartID;
        var btn = document.getElementById(this.id);
        var filename = this.props.reporttype+".png";

        btn.addEventListener('click', function () {
            saveSvgAsPng(document.getElementById(domTargetId), filename, {backgroundColor:"#FFF"});
        });
    },
    render: function() {
        return (
            <span className="loadingText">
                <a href="javascript:void(0);" title="download graph" id={this.id}>
                    <i className='fa fa-lg fa-file-image-o' aria-hidden="true"></i>
                </a>&nbsp;&nbsp;
                <a href="javascript:void(0);" title = "download CSV" onClick={this.onThisClick.bind(this)}>
                    <i className='fa fa-lg fa-file-excel-o' aria-hidden="true"></i>
                </a>
            </span>
        );
    },
    onThisClick: function(text) {
        this.props.onButtonClick();
    }
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
                <a style={inlineStyles} onClick={this.onThisClick.bind(this, this.props.buttonText)}  title="Graphical view">
                  <i className='fa fa-lg fa-area-chart' aria-hidden="true"></i>
                </a>
            );
        } else {
            return (
                <a style={inlineStyles} onClick={this.onThisClick.bind(this, this.props.buttonText)}  title="Table view">
                    <i className='fa fa-lg fa-list-ul' aria-hidden="true"></i>
                </a>
            );
        }
    },

    onThisClick: function(text) {
        this.props.onButtonClick(text);
    },
});

var Table = React.createClass({
    shouldComponentUpdate: function(nextProps) {
        this.props.activeView = nextProps.activeView;

        var nextData = JSON.stringify(nextProps.data);
        var prevData = JSON.stringify(this.props.data);
        this.forceUpdate();
        if (nextData !== prevData) {
            updateChart(
                '#' + this.props.chartID,
                nextProps.data['results'],
                nextProps.xAxisFormatter,
                nextProps.yAxisFormatter,
                nextProps.yAxisLabel,
                this.props.timezoneOffset,
                this.props.tooltipUnits,
                this.props.frontTooltip,
                this.props.chartType,
                this.props.chartID,
                nextProps.tablesColumnValueName
            );
        }
        return false;
    },
    componentDidUpdate(prevProps, prevState) {
        var nextProps = prevProps;
        // Update if we toggled a load
        updateChart(
            '#' + this.props.chartID,
            nextProps.data['results'],
            nextProps.xAxisFormatter,
            nextProps.yAxisFormatter,
            nextProps.yAxisLabel,
            this.props.timezoneOffset,
            this.props.tooltipUnits,
            this.props.frontTooltip,
            this.props.chartType,
            this.props.chartID,
            nextProps.tablesColumnValueName
        );
    },

    render: function() {
        var inlineStyles = {
            'min-height': '360px',
            'margin-top': '20px'
        };
        return (
            <div style={inlineStyles}>
                <table className={this.props.chartID} class="display table"></table>
            </div>
        );
    }
});
