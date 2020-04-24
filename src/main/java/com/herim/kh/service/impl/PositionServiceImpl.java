package com.herim.kh.service.impl;

import java.util.List;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import com.herim.kh.dao.PositionRepository;
import com.herim.kh.domain.Position;
import com.herim.kh.service.PositionService;

@Service
public class PositionServiceImpl implements PositionService {
	
	@Autowired
	private PositionRepository positionRepository;

	@Override
	public Position saveDept(Position position) {
		return positionRepository.save(position);
	}

	@Override
	public List<Position> findAllPostions() {
		return positionRepository.findAll();
	}

	
}
