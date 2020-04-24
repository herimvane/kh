package com.herim.kh.utils;

import lombok.Data;

@Data
public class Message<T> {
	
	public static final Integer OK = 0;
    public static final Integer ERROR = -1;
    public static final String MSG = "ok";

    private Integer code = ERROR;
    private String msg =  MSG;
    private String url;
    private T data;

}
