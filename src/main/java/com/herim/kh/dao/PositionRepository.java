package com.herim.kh.dao;

import org.springframework.data.jpa.repository.JpaRepository;

import com.herim.kh.domain.Position;

public interface PositionRepository extends JpaRepository<Position, String> {
	
	Position findByName(String name);
	
}
