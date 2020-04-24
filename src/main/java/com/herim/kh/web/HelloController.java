package com.herim.kh.web;

import org.springframework.stereotype.Controller;
import org.springframework.ui.ModelMap;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseBody;

@Controller
public class HelloController {

	@ResponseBody
	@RequestMapping("/hello")
	public String hello() {
		return "hello spring boot!";
	}
	
    //测试thymeleaf模版引擎
	@RequestMapping("/temp")
	public String temp (ModelMap map) {
		map.put("host", "http://www.feelfool.com");
		return "test";
	}
	
}
