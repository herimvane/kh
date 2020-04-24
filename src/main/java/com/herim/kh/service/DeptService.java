package com.herim.kh.service;

import java.util.List;

import com.herim.kh.domain.Dept;

public interface DeptService {
	
	Dept saveDept(Dept dept);
	
	List<Dept> findAllDepts();
	
	

}
