/*
 * Copyright (c) 2016-present, Facebook, Inc.
 * All rights reserved.
 *
 * This source code is licensed under the BSD-style license found in the
 * LICENSE file in the root directory of this source tree. An additional grant
 * of patent rights can be found in the PATENTS file in the same directory.
 */
  function broadcastSms() {
    var data = {
      sendto: $('input[type=radio][name="send_to"]:checked').val(),
      network_id: $('#network_id').val(),
      tower_id: $('#bts_id').val(),
      imsi: $('#imsi').val(),
      message: $('#message').val(),
      csrfmiddlewaretoken: $('#token').val(),
    };
    $.post( $('#broadcast-form').attr('action'), data, function(response) {
        
      if (response['status'] == 'ok') {
        // Show that it was successful and then reload the page.
        // Clear out any old messages and show the div again.
        $('#messages-container').html();
        $('#messages-container').css('opacity', 1);
        var html = '';
        response['messages'].map(function(message) {
          html += '<div class="alert alert-success">' + message + '</div>';
        });
        $('#messages-container').html(html).show();
        setTimeout(function() {
          location.reload();
        }, 800);
      } else {
        // Show the messages that were sent back.
        // Clear out any old messages and show the div again.
        $('#messages-container').html();
        $('#messages-container').css('opacity', 1);
        var html = '';
        response['messages'].map(function(message) {
          html += '<div class="alert alert-danger">' + message + '</div>';
        });
        if(response['imsi']) {
          $('#imsi').val(response['imsi']);
        }
        if(response['sent']) {
          html += '<div class="alert alert-success">SMS sent to ' + response['sent'] + ' IMSI(s).</div>';
        }
        $('#messages-container').html(html).show();
        setTimeout(function() {
          $('#messages-container').fadeTo(500, 0);
          $('#messages-container').hide();
        }, 4000);
      }
    });
    return false;
  }

$(document).ready(function() {

  $('input[type=radio][name="send_to"]').change(function() {
    if (this.value == 'network') {
        $('#network_row').show();
        $('#tower_row').hide();
        $('#imsi_row').hide();
    } else if (this.value == 'tower') {
        $('#network_row').hide();
        $('#tower_row').show();
        $('#imsi_row').hide();
    } else if (this.value == 'imsi') {
        $('#network_row').hide();
        $('#tower_row').hide();
        $('#imsi_row').show();
    } else {
        $('#network_row').hide();
        $('#tower_row').hide();
        $('#imsi_row').show();
    }
  });
  $('#broadcast-modal').on('shown.bs.modal', function() {
    $('#broadcast-form')[0].reset();
    $('#network_row').hide();
    $('#tower_row').hide();
    $('#imsi_row').show();
    if($('input[type=radio][name="send_to"]:checked').val()) {
        var selected = $('input[type=radio][name="send_to"]:checked').val();
        if (selected == 'network') {
            $('#network_row').show();
            $('#tower_row').hide();
            $('#imsi_row').hide();
        } else if (selected == 'tower') {
            $('#network_row').hide();
            $('#tower_row').show();
            $('#imsi_row').hide();
        } else if (selected == 'imsi') {
            $('#network_row').hide();
            $('#tower_row').hide();
            $('#imsi_row').show();
        } else {
            $('#network_row').hide();
            $('#tower_row').hide();
            $('#imsi_row').show();
        }
    }
  });
});
