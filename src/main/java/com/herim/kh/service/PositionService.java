package com.herim.kh.service;

import java.util.List;

import com.herim.kh.domain.Position;

public interface PositionService {
	
	Position saveDept(Position position);
	
	List<Position>  findAllPostions();
	
	

}
