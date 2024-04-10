// watchlist is a dict of ham callsign => symbol, packets
var watchlist = {};

function show_aprs_icon(item, symbol) {
    var offset = ord(symbol) - 33;
    var col = Math.floor(offset / 16);
    var row = offset % 16;
    //console.log("'" + symbol+"'   off: "+offset+"  row: "+ row + "   col: " + col)
    aprs_img(item, row, col);
}

function ord(str){return str.charCodeAt(0);}

function tab_string(channel, id=false) {
    name = "msgs"+channel;
    if (id) {
        return "#"+name;
    } else {
        return name;
    }
}

function tab_li_string(channel, id=false) {
    //The id of the LI containing the tab
    return tab_string(channel, id)+"Li";
}

function channel_messages_id(channel, id=false) {
    return tab_string(channel, id)+"messages";
}

function channel_users_id(channel, id=false) {
    return tab_string(channel, id)+"users";
}

function tab_notification_id(channel, id=false) {
    // The ID of the span that contains the notification count
    return tab_string(channel, id)+"notify";
}

function tab_content_name(channel, id=false) {
   return tab_string(channel, id)+"Content";
}

function content_divname(channel) {
    return "#"+tab_content_name(channel);
}

function channel_select(channel) {
    var tocall = $("#to_call");
    tocall.val(channel);
    scroll_main_content(channel);
    selected_tab_channel = channel;
    tab_notify_id = tab_notification_id(channel, true);
    $(tab_notify_id).addClass('visually-hidden');
    $(tab_notify_id).text(0);
}

function create_channel_tab(channel_obj, active=false) {
  //Create the html for the callsign tab and insert it into the DOM
  var channelTabs = $("#msgsTabList");
  channel = channel_obj["name"].replace('#', '');
  tab_id = tab_string(channel);
  tab_id_li = tab_li_string(channel);
  tab_notify_id = tab_notification_id(channel);
  tab_content = tab_content_name(channel);
  if (active) {
    active_str = "active";
  } else {
    active_str = "";
  }

  item_html = '<li class="nav-item" role="presentation" channel="'+channel+'" id="'+tab_id_li+'">';
  item_html += '<button onClick="channel_select(\''+channel+'\');" channel="'+channel+'" class="nav-link position-relative '+active_str+'" id="'+tab_id+'" data-bs-toggle="tab" data-bs-target="#'+tab_content+'" type="button" role="tab" aria-controls="'+channel+'" aria-selected="true">';
  item_html += '#'+channel+'&nbsp;&nbsp;';
  item_html += '</button></li>'

  channelTabs.append(item_html);
  create_channel_tab_content(channel_obj, active);
}

function create_channel_tab_content(channel_obj, active=false) {
  var channelTabsContent = $("#msgsTabContent");
  channel = channel_obj["name"].replace('#', '');
  tab_id = tab_string(channel);
  tab_content = tab_content_name(channel);
  channel_messages = channel_messages_id(channel);
  channel_users = channel_users_id(channel);
  if (active) {
    active_str = "show active";
  } else {
    active_str = '';
  }

  ch_messages = build_channel_messages(channel_obj);
  ch_users = build_channel_users(channel_obj);

  item_html = '<div style="height: 100%" class="tab-pane fade '+active_str+'" id="'+tab_content+'" role="tabpanel" aria-labelledby="'+tab_id+'">';
  item_html += '<div class="container text-center" style="border: 1px solid #999999;background-color:#aaaa;">';
  item_html += '  <div class="row align-items-start">';
  item_html += '    <div class="col-10" id="'+channel_messages+'" style="border-right: 1px solid #999999;">';
  item_html += '        '+ch_messages;
  item_html += '    </div>';
  item_html += '    <div class="col-2" id="'+channel_users+'">';
  item_html += '        <div class="row align-items-start"><div class="col-12" style="font-weight:bold;font-size:1.2em;">Active Users</div></div>';
  item_html += '        <div class="row align-items-start"><div class="col-12" style="font-weight:bold;color:#555555;">'+ch_users+'</div></div>';
  item_html += '    </div>';
  item_html += '  </div>';
  item_html += '</div>';

  channelTabsContent.append(item_html);
}

function build_channel_messages(channel_obj) {
    var channel = channel_obj["name"].replace('#', '');
    var messages = channel_obj["messages"];
    var messages_html = '';
    for (index in messages) {
        message = messages[index];
        messages_html += build_message(message);
    }
    return messages_html;
}

function rgb_from_string(name) {
    hash = 0
    for (let i = 0; i < name.length; i++) {
        hash = ord(name[i]) + ((hash << 5) - hash)
    }
    red = hash & 255
    green = (hash >> 8) & 255
    blue = (hash >> 16) & 255
    return "#"+red+green+blue
}

function build_message(message) {
    ts = message["timestamp"];
    console.log(ts);
    ts = ts * 1000;
    dt = new Date(message["timestamp"] * 1000);
    dt_str = $.format.date(dt, 'yyyy/MM/dd HH:mm:ss');

    callsign_color = rgb_from_string(message["from_call"]);
    console.log("callsign_color: " + callsign_color);

    var html = '<div class="row" style="border-top: 1px solid #999999;">';
    html += '<div class="col-2" style="font-size:.8em;color:green;max-width:160px;">';
    html += dt_str;
    html += '</div>';
    html += '<div class="col-2" style="font-size:.9em;color:'+callsign_color+';max-width:120px;border-left:1px solid #999999;">';
    html += message["from_call"];
    html += '</div>';
    html += '<div class="col-8" style="text-align:left;font-size: 0.8em;border-left: 1px solid #999999;">';
    html += message["message_text"];
    html += '</div>';
    html += '</div>';
    return html;
}

function build_channel_users(channel_obj) {
    var channel = channel_obj["name"].replace('#', '');
    var users = channel_obj["users"];
    var users_html = '';
    for (index in users) {
        user = users[index];
        users_html += build_user(user);
    }
    return users_html;
}

function build_user(user) {
    var callsign = user;
    var html = '<div class="row">';
    html += '<div class="col-12">';
    html += callsign;
    html += '</div>';
    html += '</div>';
    return html;
}

function init_tabs() {
    console.log("init_tabs");
    // Create the tabs for each channels
    first = true;
    console.log(channels);
    for (index in channels) {
       channel = channels[index];
       console.log(channel);
       create_channel_tab(channel, active=first);
       first = false;
    }
}

function update_tabs( data ) {

}

function update_stats( data ) {
    $("#version").text( data["aprsd"]["version"] );
    $("#aprs_connection").html( data["aprs_connection"] );
    $("#uptime").text( "uptime: " + data["aprsd"]["uptime"] );
    const html_pretty = Prism.highlight(JSON.stringify(data, null, '\t'), Prism.languages.json, 'json');
    $("#jsonstats").html(html_pretty);
}


function start_update() {
    (function statsworker() {
            $.ajax({
                url: "/stats",
                type: 'GET',
                dataType: 'json',
                success: function(data) {
                    update_stats(data);
                },
                complete: function() {
                    setTimeout(statsworker, 60000);
                }
            });
    })();
}

function scroll_main_content(channel=false) {
   var wc = $('#wc-content');
   var d = $('#msgsTabContent');
   var scrollHeight = wc.prop('scrollHeight');
   var clientHeight = wc.prop('clientHeight');

   if (channel) {
       div_id = content_divname(channel);
       c_div = $(content_divname(channel));
       //console.log("c_div("+div_id+") " + c_div);
       c_height = c_div.height();
       c_scroll_height = c_div.prop('scrollHeight');
       //console.log("callsign height " + c_height + " scrollHeight " + c_scroll_height);
       if (c_height === undefined) {
           return false;
       }
       if (c_height > clientHeight) {
           wc.animate({ scrollTop: c_scroll_height }, 500);
       } else {
           wc.animate({ scrollTop: 0 }, 500);
       }
   } else {
       if (scrollHeight > clientHeight) {
           wc.animate({ scrollTop: wc.prop('scrollHeight') }, 500);
       } else {
           wc.animate({ scrollTop: 0 }, 500);
       }
   }
}
