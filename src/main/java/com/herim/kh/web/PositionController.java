package com.herim.kh.web;

import java.util.List;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.herim.kh.domain.Position;
import com.herim.kh.service.PositionService;
import com.herim.kh.utils.Message;

@RestController
@RequestMapping("/position")
public class PositionController {
	
	@Autowired
	private PositionService positionService;

	@RequestMapping("/add")
	public Message<Position> add(@RequestBody Position position) {
		Message<Position> msg = new Message<Position>();
		positionService.saveDept(position);
		msg.setCode(Message.OK);
		return msg;
	}
	
	@RequestMapping("/list")
	public Message<List<Position>> list() {
		Message<List<Position>> msg = new Message<List<Position>>();
		List<Position> positions = positionService.findAllPostions();
		msg.setData(positions);
		msg.setCode(Message.OK);
		return msg;
	}
}
