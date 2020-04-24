package com.herim.kh.service;

import com.herim.kh.domain.Operation;

public interface OperationService {
	
	void save(Operation operation);
	Boolean haveOperation(String name, Integer status);
	void update(String name, Integer status);

}
