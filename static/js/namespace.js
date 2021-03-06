/*
 *  This Source Code Form is subject to the terms of the Mozilla Public
 *  License, v. 2.0. If a copy of the MPL was not distributed with this
 *  file, You can obtain one at http://mozilla.org/MPL/2.0/.
 *
 *  Copyright (c) 2013, OHMS Development Team
 */

var base_url = "/";
var OHMS = OHMS || {};

MathJax.Hub.Config({
    tex2jax: {
	inlineMath: [['`','`'], ['\\(','\\)']],
	processEscapes: true,
	skipTags: ["script","noscript","style","textarea","code"],
    },
});

var add_alert = function (msg) {
    $("body").append("\
<div class='alert alert-block alert-error error'>\
<button type='button' class='close' data-dismiss='alert'>&times;</button>\
<strong>Error:</strong> " + msg + "</div>");
}

$.ready(function() {
    var responses = $(".response");
    for(var i=0; i<responses.size(); i++) {
	MathJax.Hub.Queue(["Typeset", MathJax.Hub, responses.get(i)]);
    }
})


