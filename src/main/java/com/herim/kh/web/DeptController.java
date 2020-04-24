package com.herim.kh.web;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.web.bind.annotation.RestController;

import com.herim.kh.domain.Dept;
import com.herim.kh.service.DeptService;
import com.herim.kh.utils.Message;

@RestController
@RequestMapping("/dept")
public class DeptController {
	
	@Autowired
	private DeptService deptService;

	@RequestMapping("/add")
	@ResponseBody
	public Message<Object> add(@RequestBody Dept dept) {
		Message<Object> msg = new Message<Object>();
		deptService.saveDept(dept);
		msg.setCode(Message.OK);
		return msg;
	}
}
