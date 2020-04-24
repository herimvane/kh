package com.herim.kh.web;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.web.bind.annotation.RestController;

import com.herim.kh.domain.Operation;
import com.herim.kh.service.OperationService;
import com.herim.kh.utils.Message;

@RestController
@RequestMapping("/operation")
public class OperationController {
	
	@Autowired
	private OperationService operationService;
	
	@RequestMapping("/add")
	@ResponseBody
	public Message<Object> save(@RequestBody Operation operation) {
		Message<Object> msg = new Message<Object>();
		operationService.save(operation);
		msg.setCode(Message.OK);
		return msg;
	}

	@RequestMapping("/update/{name}/{status}")
	@ResponseBody
	public Message<Object> updateStatus(@PathVariable String name,@PathVariable Integer status) {
		Message<Object> msg = new Message<Object>();
		operationService.update(name, status);
		msg.setCode(Message.OK);
		return msg;
	}
}
