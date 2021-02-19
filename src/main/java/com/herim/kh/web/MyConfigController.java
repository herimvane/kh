package com.herim.kh.web;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.web.bind.annotation.RestController;

import com.herim.kh.domain.MyConfig;
import com.herim.kh.service.MyConfigService;
import com.herim.kh.utils.Message;

@RestController
@RequestMapping("/myconfig")
public class MyConfigController {
	
	@Autowired
	private MyConfigService myConfigService;
	
	@RequestMapping("/add")
	@ResponseBody
	public Message<Object> save(@RequestBody MyConfig config) {
		Message<Object> msg = new Message<Object>();
		myConfigService.save(config);
		msg.setCode(Message.OK);
		return msg;
	}

	@RequestMapping("/update/{key}/{value}")
	@ResponseBody
	public Message<Object> updateConfig(@PathVariable String key,@PathVariable String value) {
		Message<Object> msg = new Message<Object>();
		myConfigService.update(key, value);
		msg.setCode(Message.OK);
		return msg;
	}
}
