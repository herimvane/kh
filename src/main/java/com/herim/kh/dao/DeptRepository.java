package com.herim.kh.dao;

import org.springframework.data.jpa.repository.JpaRepository;

import com.herim.kh.domain.Dept;

public interface DeptRepository extends JpaRepository<Dept, String> {
	
	Dept findByName(String name);
	
}
